"""
CCSwitch AI 工具配置器
自动读写 Codex / Claude Code 等 AI 编码工具的配置文件
"""

import os
import json
import re


def get_codex_config_path() -> str | None:
    """获取 Codex config.toml 路径"""
    home = os.path.expanduser("~")
    path = os.path.join(home, ".codex", "config.toml")
    if os.path.exists(os.path.join(home, ".codex")):
        return path
    return None


def get_claude_config_path() -> str | None:
    """获取 Claude Code settings.json 路径"""
    home = os.path.expanduser("~")
    path = os.path.join(home, ".claude", "settings.json")
    if os.path.exists(os.path.join(home, ".claude")):
        return path
    return None


# ── Codex TOML 配置 ──

def configure_codex(proxy_port: int, provider_name: str, model: str,
                    wire_api: str = "responses") -> bool:
    """
    自动配置 Codex——写入 ~/.codex/config.toml

    参数:
        proxy_port: CCSwitch 代理端口
        provider_name: Provider 名称（作为 provider id 使用）
        model: 模型名
        wire_api: "chat" 或 "responses"
    """
    config_path = get_codex_config_path()
    if not config_path:
        return False

    provider_id = re.sub(r"[^a-zA-Z0-9_-]", "-", provider_name).strip("-") or "ccswitch"

    # 读取现有
    existing = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            existing["_raw"] = f.read()

    # 准备要写入/更新的字段
    new_lines = [
        f'model_provider = "{provider_id}"',
        f'model = "{model}"',
    ]

    provider_block = [
        "",
        f"[model_providers.{provider_id}]",
        f'name = "{provider_name}"',
        f'base_url = "http://127.0.0.1:{proxy_port}/v1"',
        f'wire_api = "{wire_api}"',
        "requires_openai_auth = true",
    ]

    raw = existing.get("_raw", "")
    if not raw:
        # 全新写入
        content = "\n".join(new_lines) + "\n" + "\n".join(provider_block) + "\n"
    else:
        # 更新已有配置
        content = _set_toml_value(raw, "model_provider", provider_id)
        content = _set_toml_value(content, "model", model)
        content = _upsert_toml_section(content, f"model_providers.{provider_id}", {
            "name": f'"{provider_name}"',
            "base_url": f'"http://127.0.0.1:{proxy_port}/v1"',
            "wire_api": f'"{wire_api}"',
            "requires_openai_auth": "true",
        })

    # 确保目录存在
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def _set_toml_value(toml_str: str, key: str, value: str) -> str:
    """设置 TOML 顶级 key = value"""
    if re.search(rf"^{re.escape(key)}\s*=", toml_str, re.MULTILINE):
        return re.sub(
            rf"^{re.escape(key)}\s*=.*$",
            f'{key} = "{value}"',
            toml_str,
            flags=re.MULTILINE,
        )
    else:
        return toml_str.rstrip() + f'\n{key} = "{value}"\n'


def _upsert_toml_section(toml_str: str, section: str, kv: dict) -> str:
    """
    更新或插入 TOML section（如 [model_providers.custom]）
    """
    header = f"[{section}]"
    if header in toml_str:
        # 逐 key 替换
        for k, v in kv.items():
            toml_str = _replace_in_section(toml_str, section, k, v)
        return toml_str
    else:
        # 追加新 section
        lines = [f"\n{header}"]
        for k, v in kv.items():
            lines.append(f"{k} = {v}")
        return toml_str.rstrip() + "\n" + "\n".join(lines) + "\n"


def _replace_in_section(toml_str: str, section: str, key: str, value: str) -> str:
    """在指定 TOML section 内替换 key = value"""
    header = f"[{section}]"
    # 找到 section 位置，在下一个 [section] 之前替换
    sec_start = toml_str.find(header)
    if sec_start == -1:
        return toml_str

    after_sec = toml_str[sec_start + len(header):]
    next_sec = re.search(r"\n\[", after_sec)
    if next_sec:
        sec_body = after_sec[:next_sec.start()]
        sec_rest = after_sec[next_sec.start():]
    else:
        sec_body = after_sec
        sec_rest = ""

    # 在 section body 内替换
    pattern = rf"^{re.escape(key)}\s*=.*$"
    if re.search(pattern, sec_body, re.MULTILINE):
        sec_body = re.sub(pattern, f"{key} = {value}", sec_body, flags=re.MULTILINE)
    else:
        sec_body = sec_body.rstrip() + f"\n{key} = {value}\n"

    return toml_str[:sec_start] + header + sec_body + sec_rest


# ── Claude Code JSON 配置 ──

def configure_claude_code(proxy_port: int, provider_name: str,
                          haiku_model: str = "",
                          sonnet_model: str = "",
                          opus_model: str = "") -> bool:
    """
    自动配置 Claude Code——写入 ~/.claude/settings.json

    参数:
        proxy_port: CCSwitch 代理端口
        provider_name: Provider 名称（仅备注用）
        haiku_model: Haiku 模型名
        sonnet_model: Sonnet 模型名
        opus_model: Opus 模型名
    """
    config_path = get_claude_config_path()
    if not config_path:
        return False

    # 读取现有
    cfg = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError:
            cfg = {}

    env = cfg.setdefault("env", {})

    env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{proxy_port}"
    env["ANTHROPIC_AUTH_TOKEN"] = "PROXY_MANAGED"

    if haiku_model:
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME"] = haiku_model
    if sonnet_model:
        env["ANTHROPIC_DEFAULT_SONNET_MODEL_NAME"] = sonnet_model
    if opus_model:
        env["ANTHROPIC_DEFAULT_OPUS_MODEL_NAME"] = opus_model

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    return True


# ── 一键配置（同时配置多个工具）──

def auto_configure(proxy_port: int, provider_name: str, model: str,
                   tools: list[str] | None = None) -> dict:
    """
    一键配置：自动配置 Provider + Codex + Claude Code

    返回: {"codex": True/False, "claude": True/False}
    """
    if tools is None:
        tools = ["codex", "claude"]

    result = {}

    if "codex" in tools:
        result["codex"] = configure_codex(proxy_port, provider_name, model)

    if "claude" in tools:
        result["claude"] = configure_claude_code(
            proxy_port, provider_name,
            haiku_model=model,
            sonnet_model=model,
        )

    return result
