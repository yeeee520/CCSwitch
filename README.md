<h1 align="center">CCSwitch</h1>

<p align="center">
  <strong>AI 编码代理桌面工具</strong><br>
  一键路由 · 多 Provider 切换 · 协议自动转换
</p>

<p align="center">
  <img src="icon.png" width="128" height="128" alt="CCSwitch">
</p>

---

## 简介

**CCSwitch** 是一款 Windows 桌面端 AI 编码代理工具，专为 AI 编码工具（如 Codex、Claude Code 等）设计。它运行一个本地反向代理服务器，让你可以：

- 将不同 AI 模型路由到不同的 API Provider（OpenAI、Anthropic、DeepSeek 等）
- 自动转换 Codex `/v1/responses` 协议与 OpenAI `/v1/chat/completions` 协议
- 通过桌面 GUI 可视化管理 Provider 和路由规则
- 一键配置 AI 编码工具的 API 端点

## 界面一览

CCSwitch 提供 4 个功能标签页：

| 标签页 | 功能 |
|--------|------|
| **控制台** | 启停代理、查看状态、运行统计、使用指引 |
| **API Keys** | 管理多个 API Provider（名称、Base URL、Key、模型列表） |
| **路由规则** | 配置模型名到 Provider 的匹配规则，支持通配符 |
| **请求日志** | 实时查看 API 请求的转发状态和响应码 |

底部固定栏支持一键切换默认 Provider 并自动写入 Codex / Claude Code 配置。

## 核心特性

- **多 Provider 动态路由** — 支持 OpenAI、Anthropic、DeepSeek 等任意 API Provider，基于通配符模型名自动匹配路由规则
- **协议自动转换** — 兼容 OpenAI Chat Completions 和 Codex Responses 双协议格式，支持 SSE 流式转发并保留推理内容渲染
- **桌面 GUI** — 基于 Python + CustomTkinter 构建，暗色主题，4 个功能标签页，实时日志展示
- **系统托盘常驻** — 关闭窗口后最小化到系统托盘，后台静默运行，右键菜单一键控制
- **一键工具配置** — 自动写入 `~/.codex/config.toml` 和 `~/.claude/settings.json`，无缝切换 API 端点
- **独立分发** — 使用 PyInstaller 打包为独立 exe，无需 Python 环境，首次运行自动在 `%APPDATA%` 生成配置

## 快速开始

### 下载运行

从 [Releases](https://github.com/yeeee520/CCSwitch/releases) 下载最新版 `CCSwitch.exe`，双击即可运行。

> 首次运行会自动在 `%APPDATA%\CCSwitch\` 生成配置文件和图标，不会污染 exe 所在目录。

### 从源码运行

```bash
# 克隆仓库
git clone https://github.com/yeeee520/CCSwitch.git
cd CCSwitch

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

## 使用教程（以 DeepSeek 为例）

### 第 1 步：添加 Provider

1. 切换到 **API Keys** 标签页
2. 点击 **+ 添加 Provider**
3. 填写：

| 字段 | 值 |
|------|-----|
| 名称 | `DeepSeek` |
| Base URL | `https://api.deepseek.com` |
| API Key | 你的 DeepSeek API Key |
| 模型列表 | `deepseek-chat` |

4. 点击保存

### 第 2 步：一键配置 Codex

窗口底部快速接入栏：

- 工具选 **Codex**
- 模型名填 `deepseek-chat`
- Provider 选 **DeepSeek**
- 点击 **写入配置**

> 这会自动修改 `~/.codex/config.toml`，将 Codex 的 API 请求指向本代理。

### 第 3 步：启动代理

1. 切换到 **控制台** 标签
2. 确认端口（默认 3456）
3. 点击 **启动代理**

状态灯变绿即可。然后重启 Codex 就能用了。

## 配置文件

配置文件保存在 `%APPDATA%\CCSwitch\config.json`：

```json
{
  "proxyPort": 3456,
  "providers": [
    {
      "id": "p-xxx",
      "name": "DeepSeek",
      "baseUrl": "https://api.deepseek.com",
      "apiKey": "sk-xxx",
      "models": "deepseek-chat"
    }
  ],
  "rules": [
    {
      "id": "r-xxx",
      "name": "DeepSeek 路由",
      "modelPattern": "deepseek*",
      "providerId": "p-xxx",
      "modelOverride": "deepseek-chat"
    }
  ]
}
```

> 配置文件包含 API Key，**不要**提交到公开仓库。仓库中已提供 `config.example.json` 作为模板。

## API 端点

代理服务器启动后，暴露以下本地端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/chat/completions` | OpenAI 兼容格式 |
| POST | `/v1/responses` | Codex 专用端点 |
| GET | `/v1/models` | 模型列表 |
| GET | `/api/config` | 获取配置 |
| PUT | `/api/config` | 更新配置 |

## 技术栈

- **Python 3.12** — 核心语言
- **CustomTkinter** — 桌面 GUI 框架
- **Flask** — 反向代理服务器
- **pystray** — 系统托盘图标
- **PyInstaller** — exe 打包分发

## 常见问题

**Q: Codex 报 404 Not Found？**
确保已勾选 Codex 使用 `wire_api = "responses"`，代理服务器已支持该端点。

**Q: 端口被占用？**
在控制台修改端口号后重启代理。

**Q: 如何查看请求是否成功？**
切换到**请求日志**标签页，实时显示每个请求的状态码。

## License

MIT
