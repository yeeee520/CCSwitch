"""
CCSwitch 代理服务器
Flask 应用，运行在独立线程，负责 API 转发
"""

import json
import queue
import threading
import time
from flask import Flask, request, Response, jsonify, stream_with_context
import requests


def create_proxy_app(config_loader, log_queue: queue.Queue):
    """
    创建并返回 Flask 应用。
    config_loader: 无参函数，返回当前配置 dict（保证线程安全读取）
    log_queue: 日志队列，GUI 端从中取出日志
    """
    app = Flask(__name__)

    # ── CORS 支持 ──
    @app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        return response

    @app.before_request
    def handle_options():
        if request.method == "OPTIONS":
            return "", 200

    # ── 帮助函数 ──
    def _add_log(model: str, ua: str, rule_name: str, status: int):
        """向日志队列写入一条记录"""
        entry = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": model,
            "ua": ua,
            "rule": rule_name,
            "status": status,
        }
        try:
            log_queue.put_nowait(entry)
        except queue.Full:
            pass  # 如果队列满了就丢弃

    # ── 格式转换工具 ──

    def _responses_to_chat(data: dict) -> dict:
        """将 /v1/responses 请求转换为 /v1/chat/completions 格式"""
        result = {}

        # model
        result["model"] = data.get("model", "")

        # messages: input + instructions → messages
        messages = []
        instructions = data.get("instructions", "")
        inp = data.get("input", "")

        if instructions:
            messages.append({"role": "system", "content": instructions})

        if isinstance(inp, str):
            messages.append({"role": "user", "content": inp})
        elif isinstance(inp, list):
            for item in inp:
                role = item.get("role", "user")
                content = item.get("content")
                if content is None:
                    content = ""
                # content may be a list of content parts (Codex format)
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict):
                            ptype = part.get("type", "")
                            if ptype in ("input_text", "text"):
                                text_parts.append(part.get("text", ""))
                    content = "\n".join(text_parts) if text_parts else ""
                elif not isinstance(content, str):
                    # content may be a dict or other non-string type
                    content = str(content)
                if role == "developer":
                    role = "system"
                if not content:
                    continue  # skip empty messages
                messages.append({"role": role, "content": content})
        elif inp:
            # fallback: input could be a dict
            messages.append({"role": "user", "content": str(inp)})

        result["messages"] = messages

        # reasoning
        reasoning = data.get("reasoning")
        if reasoning and isinstance(reasoning, dict):
            effort = reasoning.get("effort")
            if effort:
                result["reasoning_effort"] = effort

        # common params
        for key in ("temperature", "top_p", "max_output_tokens", "stream",
                     "stop", "frequency_penalty", "presence_penalty"):
            if key in data:
                if key == "max_output_tokens":
                    result["max_tokens"] = data[key]
                else:
                    result[key] = data[key]

        # tools: responses format → chat completions format
        # DeepSeek only supports type="function" — strip everything else
        tools = data.get("tools", [])
        if tools:
            chat_tools = []
            for t in tools:
                ttype = t.get("type", "")
                if ttype == "function":
                    params = t.get("parameters", {})
                    # DeepSeek requires parameters to be a valid JSON Schema object
                    if not isinstance(params, dict) or not params:
                        params = {"type": "object", "properties": {}}
                    if "type" not in params:
                        params["type"] = "object"
                    chat_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.get("name", ""),
                            "description": t.get("description", ""),
                            "parameters": params,
                        }
                    })
                # web_search_preview, file_search, namespace, code_interpreter etc
                # are all unsupported by DeepSeek — silently drop them
            result["tools"] = chat_tools

        if "tool_choice" in data:
            result["tool_choice"] = data["tool_choice"]

        return result

    def _chat_to_responses(chat_resp: dict, model: str, request_id: str = "") -> dict:
        """将 /v1/chat/completions 响应转换为 /v1/responses 格式"""
        resp = {
            "id": chat_resp.get("id", f"resp_{int(time.time())}"),
            "object": "response",
            "created_at": chat_resp.get("created", int(time.time())),
            "status": "completed",
            "model": model,
            "output": [],
            "usage": None,
        }

        if request_id:
            resp["id"] = request_id

        # usage
        usage = chat_resp.get("usage", {})
        if usage:
            resp["usage"] = {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            }
            details = usage.get("prompt_tokens_details", {}) or {}
            if details.get("cached_tokens"):
                resp["usage"]["input_tokens_details"]["cached_tokens"] = details["cached_tokens"]
            completion_details = usage.get("completion_tokens_details", {}) or {}
            if completion_details.get("reasoning_tokens"):
                resp["usage"]["output_tokens_details"]["reasoning_tokens"] = completion_details["reasoning_tokens"]

        # choices → output
        choices = chat_resp.get("choices", [])
        for choice in choices:
            msg = choice.get("message", {})
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            tool_calls = msg.get("tool_calls", [])

            # 合并 reasoning 到正文前面，加模型标签
            full_content = f"[📡 {model}]\n\n"
            if reasoning:
                full_content += reasoning + "\n\n"
            full_content += content

            if content.strip() or reasoning.strip():
                resp["output"].append({
                    "id": f"msg_{int(time.time()*1000)}",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{
                        "type": "output_text",
                        "text": full_content,
                        "annotations": [],
                    }],
                })

            for tc in tool_calls:
                fn = tc.get("function", {})
                resp["output"].append({
                    "id": tc.get("id", f"fc_{int(time.time()*1000)}"),
                    "type": "function_call",
                    "status": "completed",
                    "call_id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", ""),
                })

        if not resp["output"]:
            resp["output"].append({
                "id": f"msg_{int(time.time()*1000)}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "", "annotations": []}],
            })

        return resp

    def _stream_chat_to_responses(resp, model: str, request_id: str):
        """将 chat/completions SSE 流转为 responses SSE 流"""
        resp_id = request_id or f"resp_{int(time.time()*1000)}"
        msg_id = f"msg_{int(time.time()*1000)}"
        created_at = int(time.time())

        text = ""
        reasoning = ""
        tool_calls = {}  # index -> {id, name, arguments}
        finish_reason = None
        usage = None
        setup_emitted = False

        def _emit(event_type, data):
            return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        resp.encoding = "utf-8"

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if not setup_emitted:
                    setup_emitted = True
                    yield _emit("response.created", {
                        "type": "response.created",
                        "response": {"id": resp_id, "object": "response", "created_at": created_at,
                                     "status": "in_progress", "model": model, "output": [], "usage": None}
                    })
                    yield _emit("response.in_progress", {
                        "type": "response.in_progress",
                        "response": {"id": resp_id, "object": "response", "created_at": created_at,
                                     "status": "in_progress", "model": model, "output": [], "usage": None}
                    })
                    yield _emit("response.output_item.added", {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {"id": msg_id, "type": "message", "status": "in_progress",
                                 "role": "assistant", "content": []}
                    })
                    yield _emit("response.content_part.added", {
                        "type": "response.content_part.added",
                        "item_id": msg_id, "output_index": 0, "content_index": 0,
                        "part": {"type": "output_text", "text": "", "annotations": []}
                    })

                choices = chunk.get("choices", []) or []
                for choice in (choices if isinstance(choices, list) else []):
                    delta = choice.get("delta") or {}
                    rc = delta.get("reasoning_content", "")
                    if rc:
                        reasoning += rc
                        yield _emit("response.output_text.delta", {
                            "type": "response.output_text.delta",
                            "item_id": msg_id, "output_index": 0, "content_index": 0,
                            "delta": rc
                        })

                    c = delta.get("content", "")
                    if c:
                        text += c
                        yield _emit("response.output_text.delta", {
                            "type": "response.output_text.delta",
                            "item_id": msg_id, "output_index": 0, "content_index": 0,
                            "delta": c
                        })

                    for tc in (delta.get("tool_calls") or []):
                        idx = tc.get("index", 0)
                        if idx not in tool_calls:
                            tool_calls[idx] = {"id": tc.get("id", ""), "name": "", "arguments": ""}
                        if tc.get("id"):
                            tool_calls[idx]["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_calls[idx]["name"] += fn["name"]
                        if fn.get("arguments"):
                            tool_calls[idx]["arguments"] += fn["arguments"]

                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]

                if chunk.get("usage"):
                    usage = chunk["usage"]

        # Build full text — 模型标签放在最前面
        body = (reasoning + "\n\n" + text).strip() if reasoning else text
        full_text = f"[📡 {model}]\n\n{body}" if body else f"[📡 {model}]"

        # content_part.done
        yield _emit("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": msg_id, "output_index": 0, "content_index": 0,
            "part": {"type": "output_text", "text": full_text, "annotations": []}
        })

        # output_item.done for message
        msg_content = [{"type": "output_text", "text": full_text, "annotations": []}] if full_text else []
        yield _emit("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {"id": msg_id, "type": "message", "status": "completed",
                     "role": "assistant", "content": msg_content}
        })

        # Build final output list
        output_list = []
        if full_text or not tool_calls:
            output_list.append({
                "id": msg_id, "type": "message", "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": full_text, "annotations": []}]
            })

        for i, idx in enumerate(sorted(tool_calls.keys())):
            tc = tool_calls[idx]
            output_list.append({
                "id": tc["id"] or f"fc_{int(time.time()*1000)}",
                "type": "function_call", "status": "completed",
                "call_id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]
            })

        # Build final response
        final_resp = {
            "id": resp_id, "object": "response", "created_at": created_at,
            "status": "completed", "model": model, "output": output_list, "usage": None
        }
        if usage:
            final_resp["usage"] = {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            }
            details = usage.get("prompt_tokens_details", {}) or {}
            if details.get("cached_tokens"):
                final_resp["usage"]["input_tokens_details"]["cached_tokens"] = details["cached_tokens"]
            cd = usage.get("completion_tokens_details", {}) or {}
            if cd.get("reasoning_tokens"):
                final_resp["usage"]["output_tokens_details"]["reasoning_tokens"] = cd["reasoning_tokens"]

        yield _emit("response.completed", {
            "type": "response.completed",
            "response": final_resp
        })

        yield "data: [DONE]\n\n"

    # ── POST /v1/chat/completions ──
    @app.route("/v1/chat/completions", methods=["POST"])
    def chat_completions():
        return _handle_api_request(request.path)

    # ── POST /v1/responses ── (Codex 专用)
    @app.route("/v1/responses", methods=["POST"])
    def responses_api():
        return _handle_api_request(request.path)

    def _handle_api_request(path: str):
        cfg = config_loader()
        data = request.get_json(force=True, silent=True)
        if data is None:
            return jsonify({"error": {"message": "Invalid JSON body"}}), 400

        is_responses = path == "/v1/responses"
        request_id = data.get("id", "")

        # 格式转换: responses → chat completions
        if is_responses:
            data = _responses_to_chat(data)

        model = data.get("model", "")
        is_stream = data.get("stream", False)
        ua = request.headers.get("User-Agent", "")

        # 查找匹配规则
        from config_manager import find_matching_rule, get_provider
        rule = find_matching_rule(cfg, model)
        if rule is None:
            _add_log(model, ua, "No match", 400)
            return jsonify({"error": {"message": f"No route for model: {model}"}}), 400

        provider = get_provider(cfg, rule["providerId"])
        if provider is None:
            _add_log(model, ua, rule.get("name", "?"), 400)
            return jsonify({"error": {"message": f"Provider not found: {rule['providerId']}"}}), 400

        api_key = provider.get("apiKey", "")
        if not api_key:
            _add_log(model, ua, rule.get("name", "?"), 400)
            return jsonify({"error": {"message": f"No API key configured for: {provider['name']}"}}), 400

        # 模型名覆盖
        effective_model = data["model"]
        if rule.get("modelOverride"):
            effective_model = rule["modelOverride"]
            data["model"] = effective_model

        base_url = provider["baseUrl"].rstrip("/")
        # 如果 baseUrl 已经以 /v1 结尾，不要再拼一遍
        if base_url.endswith("/v1"):
            target_url = f"{base_url}/chat/completions"
        else:
            target_url = f"{base_url}/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": ua,
        }

        try:
            resp = requests.post(
                target_url,
                headers=headers,
                json=data,
                stream=is_stream,
                timeout=120,
            )
        except requests.exceptions.Timeout:
            _add_log(model, ua, rule.get("name", "?"), 502)
            return jsonify({"error": {"message": "Upstream timeout"}}), 502
        except requests.exceptions.RequestException as e:
            _add_log(model, ua, rule.get("name", "?"), 502)
            return jsonify({"error": {"message": f"Proxy error: {e}"}}), 502

        status = resp.status_code
        _add_log(model, ua, rule.get("name", "?"), status)

        # 上游错误 → 直接透传错误 body，不做格式转换
        if status >= 400:
            error_body = resp.text
            try:
                error_body = resp.json()
            except Exception:
                pass
            return jsonify(error_body) if isinstance(error_body, dict) else (error_body, status,
                   {"Content-Type": resp.headers.get("Content-Type", "application/json")})

        if is_stream:
            if is_responses:
                # 转换 DeepSeek SSE → Codex responses SSE
                def generate_responses():
                    try:
                        for sse_chunk in _stream_chat_to_responses(resp, effective_model, request_id):
                            yield sse_chunk.encode("utf-8") if isinstance(sse_chunk, str) else sse_chunk
                    finally:
                        resp.close()
                return Response(
                    stream_with_context(generate_responses()),
                    status=status,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                    },
                )
            else:
                def generate():
                    try:
                        for chunk in resp.iter_content(chunk_size=4096):
                            if chunk:
                                yield chunk
                    finally:
                        resp.close()
                return Response(
                    stream_with_context(generate()),
                    status=status,
                    headers={
                        "Content-Type": resp.headers.get("Content-Type", "text/event-stream"),
                        "Cache-Control": resp.headers.get("Cache-Control", "no-cache"),
                    },
                )
        else:
            # 非流式响应
            body = resp.json() if resp.status_code < 400 else None
            if body and is_responses:
                # 转换回 responses 格式
                body = _chat_to_responses(body, effective_model, request_id)
                return jsonify(body), status
            return resp.content, status, {"Content-Type": "application/json"}

    # ── GET /v1/models ──
    @app.route("/v1/models", methods=["GET"])
    def list_models():
        cfg = config_loader()
        models = []
        for prov in cfg.get("providers", []):
            model_str = prov.get("models", "")
            if model_str:
                for m in model_str.split(","):
                    m = m.strip()
                    if m:
                        models.append({
                            "id": m,
                            "object": "model",
                            "created": 1,
                            "owned_by": prov.get("name", "proxy"),
                        })
        return jsonify({"object": "list", "data": models})

    # ── GET /api/config ──
    @app.route("/api/config", methods=["GET"])
    def get_config():
        from config_manager import sanitize_config
        return jsonify(sanitize_config(config_loader()))

    # ── PUT /api/config ──
    @app.route("/api/config", methods=["PUT"])
    def update_config():
        cfg = config_loader()
        new_cfg = request.get_json(force=True, silent=True)
        if new_cfg is None:
            return jsonify({"error": "Invalid JSON"}), 400

        # API Key 脱敏保护：如果 Key 包含 "..." 则保留旧值
        old_providers = {p["id"]: p for p in cfg.get("providers", [])}
        for np in new_cfg.get("providers", []):
            if np.get("apiKey", "") and "..." in np["apiKey"]:
                old = old_providers.get(np["id"])
                if old:
                    np["apiKey"] = old.get("apiKey", "")

        # 写回完整配置
        for key in ("proxyPort", "providers", "rules"):
            if key in new_cfg:
                cfg[key] = new_cfg[key]

        from config_manager import save_config
        save_config(cfg)
        return jsonify({"success": True})

    # ── GET /api/logs ──
    @app.route("/api/logs", methods=["GET"])
    def get_logs():
        # 从队列中导出所有日志（非破坏性）
        # 注意：这里只是粗略导出；GUI 应自己维护日志列表
        return jsonify([])

    # ── POST /api/logs/clear ──
    @app.route("/api/logs/clear", methods=["POST"])
    def clear_logs():
        # 清空日志由 GUI 自行管理；这里返回成功
        return jsonify({"success": True})

    return app


class ProxyServer:
    """代理服务器 wrapper —— 管理 Flask 线程的启停"""

    def __init__(self, config_loader, log_queue: queue.Queue):
        self.config_loader = config_loader
        self.log_queue = log_queue
        self.app = create_proxy_app(config_loader, log_queue)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self, port: int = 3456):
        """在后台线程启动 Flask"""
        if self._thread and self._thread.is_alive():
            return  # 已经在运行
        self._stop_event.clear()

        def _run():
            self.app.run(
                host="127.0.0.1",
                port=port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self):
        """请求停止（Flask 开发服务器没有优雅关闭，这里靠标记位）"""
        self._stop_event.set()
        # Flask 开发服务器在 daemon 线程中，主线程退出时自动结束
        # 如果需要强制关闭，可以通过 werkzeug 内部实现
        from flask import request
        try:
            # 发送一个本地请求以触发 shutdown（可选）
            pass
        except Exception:
            pass

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
