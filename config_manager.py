"""
CCSwitch 配置管理器
负责 config.json 的读写、Provider 查找、路由规则匹配
"""

import json
import os
import re
import time


# 默认配置（首次启动时生成）
DEFAULT_CONFIG = {
    "proxyPort": 3456,
    "providers": [
        {
            "id": "p-default-openai",
            "name": "OpenAI",
            "baseUrl": "https://api.openai.com",
            "apiKey": "",
            "models": "gpt-4o,gpt-4o-mini,gpt-4o-turbo",
        },
        {
            "id": "p-default-anthropic",
            "name": "Anthropic",
            "baseUrl": "https://api.anthropic.com",
            "apiKey": "",
            "models": "claude-sonnet-4-20250514,claude-sonnet-4",
        },
    ],
    "rules": [
        {
            "id": "r-default-gpt4o",
            "name": "GPT-4o 路由到 OpenAI",
            "modelPattern": "gpt-4o*",
            "providerId": "p-default-openai",
            "modelOverride": "",
        },
        {
            "id": "r-default-claude",
            "name": "Claude 路由到 Anthropic",
            "modelPattern": "claude-*",
            "providerId": "p-default-anthropic",
            "modelOverride": "",
        },
        {
            "id": "default",
            "name": "默认路由",
            "modelPattern": "*",
            "providerId": "p-default-openai",
            "modelOverride": "",
        },
    ],
}


def _make_id(prefix: str) -> str:
    """生成简单唯一 ID"""
    return f"{prefix}-{int(time.time() * 1000)}"


def load_config(config_path: str = "config.json") -> dict:
    """加载配置；文件不存在时返回默认配置"""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 确保必要字段存在
            cfg.setdefault("proxyPort", 3456)
            cfg.setdefault("providers", [])
            cfg.setdefault("rules", [])
            return cfg
        except (json.JSONDecodeError, IOError):
            pass
    # 返回深拷贝的默认配置
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(config: dict, config_path: str = "config.json"):
    """保存配置到 JSON 文件"""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_provider(config: dict, provider_id: str) -> dict | None:
    """根据 ID 查找 Provider"""
    for p in config.get("providers", []):
        if p["id"] == provider_id:
            return p
    return None


def find_matching_rule(config: dict, model_name: str) -> dict | None:
    """按优先级查找第一个匹配的路由规则；支持 * 通配符"""
    for rule in config.get("rules", []):
        pattern = rule["modelPattern"]
        if pattern == "*":
            # 默认规则最后匹配
            continue
        # 将通配符模式转正则
        escaped = re.escape(pattern).replace(r"\*", ".*")
        try:
            if re.match("^" + escaped + "$", model_name, re.IGNORECASE):
                return rule
        except re.error:
            continue

    # 回退到默认规则（modelPattern == "*"）
    for rule in config.get("rules", []):
        if rule["modelPattern"] == "*":
            return rule
    return None


def mask_api_key(key: str) -> str:
    """脱敏 API Key：显示前4位+...后4位；不足8位全隐藏"""
    if not key:
        return ""
    if len(key) > 8:
        return key[:4] + "..." + key[-4:]
    return "***"


def sanitize_config(config: dict) -> dict:
    """返回脱敏后的配置（API Key 隐藏）"""
    safe = json.loads(json.dumps(config))
    for p in safe.get("providers", []):
        p["apiKey"] = mask_api_key(p.get("apiKey", ""))
    return safe
