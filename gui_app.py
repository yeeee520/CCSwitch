"""
CCSwitch GUI 主界面
CustomTkinter 实现：4 个 Tab（控制台 / API Keys / 路由规则 / 请求日志）
"""

import os
import queue
import threading
import time
import customtkinter as ct
from tkinter import messagebox, filedialog


# ── 主题设置 ──
ct.set_appearance_mode("dark")
ct.set_default_color_theme("dark-blue")

# 颜色常量
GREEN = "#22C55E"
RED = "#EF4444"
ORANGE = "#F59E0B"
CYAN = "#00E5FF"
DARK_BG = "#1a1a2e"
CARD_BG = "#16213e"


class CCSwitchApp:
    """主应用窗口"""

    def __init__(
        self,
        config: dict,
        config_path: str,
        log_queue: queue.Queue,
        on_start_proxy,
        on_stop_proxy,
        on_exit,
        tray_icon,
    ):
        self.config = config
        self.config_path = config_path
        self.log_queue = log_queue
        self._on_start_proxy = on_start_proxy
        self._on_stop_proxy = on_stop_proxy
        self._on_exit = on_exit
        self._tray_icon = tray_icon

        self._proxy_running = False
        self._start_time: float | None = None
        self._logs: list = []  # 本地日志缓存
        self._runtime_timer_id: str | None = None

        # 创建主窗口
        self.window = ct.CTk()
        self.window.title("CCSwitch - AI 编码代理")
        self.window.geometry("850x620")
        self.window.minsize(700, 500)

        # 窗口居中
        self._center_window()

        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if os.path.exists(icon_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(icon_path)
                tk_img = ImageTk.PhotoImage(img.resize((32, 32)))
                self.window.iconphoto(True, tk_img)
                self._tk_icon = tk_img  # 保持引用防止 GC
            except Exception:
                pass

        # 拦截关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 窗口置顶
        self.window.attributes("-topmost", True)
        self.window.after(500, lambda: self.window.attributes("-topmost", False))

        # ── 构建 UI ──
        self._build_ui()

        # ── 启动日志轮询 ──
        self._poll_logs()

    # ═══════════════════════════════════════════
    # 窗口管理
    # ═══════════════════════════════════════════

    def _center_window(self):
        self.window.update_idletasks()
        w = 850
        h = 620
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.window.geometry(f"{w}x{h}+{x}+{y}")

    def _on_close(self):
        """关闭窗口 → 隐藏到托盘（仅在有托盘时）"""
        if self._tray_icon:
            self.window.withdraw()
            self._tray_icon.notify("CCSwitch", "程序已最小化到系统托盘")
        else:
            self._do_exit()

    def show_window(self):
        """显示并置顶窗口"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _do_exit(self):
        """安全退出"""
        self.window.destroy()
        self._on_exit()

    # ═══════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════

    def _build_ui(self):
        # ── 顶部 Tab 栏 ──
        self.tab_frame = ct.CTkFrame(self.window, fg_color=DARK_BG, height=48)
        self.tab_frame.pack(fill="x", padx=0, pady=0)
        self.tab_frame.pack_propagate(False)

        tab_names = ["⚡ 控制台", "🔑 API Keys", "📡 路由规则", "📋 请求日志"]
        self._tab_buttons = []
        self._tab_frames = []

        for i, name in enumerate(tab_names):
            btn = ct.CTkButton(
                self.tab_frame,
                text=name,
                width=160,
                height=38,
                font=ct.CTkFont(size=13, weight="bold"),
                fg_color=CARD_BG if i > 0 else CYAN,
                text_color="#ffffff" if i > 0 else "#000000",
                hover_color="#0F3460",
                corner_radius=8,
                command=lambda idx=i: self._switch_tab(idx),
            )
            btn.pack(side="left", padx=3, pady=5)
            self._tab_buttons.append(btn)

        # ── Tab 内容区 ──
        self.content_frame = ct.CTkFrame(self.window, fg_color=DARK_BG)
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 0))

        # ── 快速接入栏（固定在底部，不随 Tab 切换隐藏）──
        self._build_quick_bar()

        self._build_console_tab()
        self._build_keys_tab()
        self._build_rules_tab()
        self._build_logs_tab()

        self._switch_tab(0)

    def _switch_tab(self, idx: int):
        """切换 Tab"""
        for i, btn in enumerate(self._tab_buttons):
            if i == idx:
                btn.configure(fg_color=CYAN, text_color="#000000")
            else:
                btn.configure(fg_color=CARD_BG, text_color="#ffffff")

        for i, frame in enumerate(self._tab_frames):
            if i == idx:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        self._current_tab = idx

    # ═══════════════════════════════════════════
    # Tab 1: 控制台
    # ═══════════════════════════════════════════

    def _build_console_tab(self):
        frame = ct.CTkScrollableFrame(self.content_frame, fg_color="transparent")
        self._tab_frames.append(frame)

        # ── 状态区 ──
        status_row = ct.CTkFrame(frame, fg_color="transparent")
        status_row.pack(fill="x", pady=(20, 15))

        # 状态指示灯（用 Canvas 手动绘制圆形）
        self._status_canvas = ct.CTkCanvas(
            status_row, width=28, height=28,
            bg=DARK_BG, highlightthickness=0,
        )
        self._status_canvas.pack(side="left", padx=(20, 8))
        self._status_dot = self._status_canvas.create_oval(4, 4, 24, 24, fill=RED, outline="")

        self._status_label = ct.CTkLabel(
            status_row, text="代理已停止",
            font=ct.CTkFont(size=18, weight="bold"),
        )
        self._status_label.pack(side="left", padx=4)

        # ── 端口 + 启停按钮 ──
        ctrl_row = ct.CTkFrame(frame, fg_color="transparent")
        ctrl_row.pack(fill="x", pady=(0, 15))

        ct.CTkLabel(ctrl_row, text="端口:", font=ct.CTkFont(size=13)).pack(side="left", padx=(20, 6))
        self._port_var = ct.StringVar(value=str(self.config.get("proxyPort", 3456)))
        self._port_entry = ct.CTkEntry(ctrl_row, width=70, textvariable=self._port_var)
        self._port_entry.pack(side="left", padx=4)

        self._toggle_btn = ct.CTkButton(
            ctrl_row, text="▶  启动代理", width=130, height=34,
            font=ct.CTkFont(size=13, weight="bold"),
            fg_color=GREEN, hover_color="#16A34A",
            command=self._toggle_proxy,
            state="normal",
        )
        self._toggle_btn.pack(side="left", padx=20)

        # ── 统计卡片 ──
        cards_row = ct.CTkFrame(frame, fg_color="transparent")
        cards_row.pack(fill="x", pady=(5, 15))

        self._card_runtime = self._make_card(cards_row, "运行时间", "00小时00分")
        self._card_rules = self._make_card(cards_row, "已配置路由", "0")
        self._card_requests = self._make_card(cards_row, "总请求数", "0")
        self._card_address = self._make_card(cards_row, "代理地址", "http://127.0.0.1:3456")

        # ── 使用指引 ──
        guide_frame = ct.CTkFrame(frame, fg_color=CARD_BG, corner_radius=12)
        guide_frame.pack(fill="x", padx=20, pady=(10, 10))

        ct.CTkLabel(
            guide_frame, text="📖 使用指引",
            font=ct.CTkFont(size=15, weight="bold"),
            text_color=CYAN,
        ).pack(anchor="w", padx=20, pady=(15, 8))

        steps = [
            "① 在「API Keys」中添加 Provider（如 OpenAI、Anthropic），填入 API Key",
            "② 在「路由规则」中设置模型匹配规则，指定走哪个 Provider",
            "③ 在你的 AI 编码工具中，把 API 地址指向本代理 → http://127.0.0.1:端口",
        ]
        for s in steps:
            ct.CTkLabel(
                guide_frame, text=s,
                font=ct.CTkFont(size=12),
                text_color="#94a3b8",
            ).pack(anchor="w", padx=30, pady=2)

        ct.CTkLabel(guide_frame, text="").pack()  # spacer

    def _build_quick_bar(self):
        """固定在窗口底部的快速接入栏 — Provider 一键切换开关"""
        bar = ct.CTkFrame(self.window, fg_color=CARD_BG, height=52)
        bar.pack(fill="x", side="bottom", padx=10, pady=(0, 6))
        bar.pack_propagate(False)

        inner = ct.CTkFrame(bar, fg_color="transparent")
        inner.pack(expand=True, pady=4)

        ct.CTkLabel(inner, text="🚀 切换 Provider:", font=ct.CTkFont(size=12, weight="bold"),
                    text_color=CYAN).pack(side="left", padx=(12, 6))

        # Provider 开关按钮容器
        self._provider_switch_frame = ct.CTkFrame(inner, fg_color="transparent")
        self._provider_switch_frame.pack(side="left", padx=2)

        self._provider_switches: dict = {}  # provider_id -> btn
        self._active_provider_id: str | None = None

        # 工具选择
        ct.CTkLabel(inner, text="工具", font=ct.CTkFont(size=11)).pack(side="left", padx=(16, 2))
        self._tool_var = ct.StringVar(value="Codex")
        ct.CTkOptionMenu(inner, width=100, variable=self._tool_var,
                         values=["Codex", "Codex + Claude Code"],
                         height=26).pack(side="left", padx=(0, 12))

        self._quick_btn = ct.CTkButton(
            inner, text="⚡ 写入配置", width=100, height=30,
            font=ct.CTkFont(size=12, weight="bold"),
            fg_color=CYAN, text_color="#000000", hover_color="#22D3EE",
            command=self._quick_configure,
        )
        self._quick_btn.pack(side="left", padx=4)

        self._quick_status = ct.CTkLabel(inner, text="", font=ct.CTkFont(size=11), text_color=GREEN)
        self._quick_status.pack(side="left", padx=12)

        self._refresh_provider_switches()

    def _make_card(self, parent: ct.CTkFrame, title: str, value: str) -> ct.CTkFrame:
        """创建统计卡片"""
        card = ct.CTkFrame(parent, fg_color=CARD_BG, corner_radius=10, width=180, height=80)
        card.pack(side="left", padx=6, expand=True, fill="x")
        card.pack_propagate(False)

        ct.CTkLabel(
            card, text=title,
            font=ct.CTkFont(size=11), text_color="#94a3b8",
        ).pack(pady=(12, 2))

        lbl = ct.CTkLabel(
            card, text=value,
            font=ct.CTkFont(size=16, weight="bold"), text_color="#ffffff",
        )
        lbl.pack()

        # 把 value label 存到 card 上方便更新
        card._value_label = lbl
        return card

    # ═══════════════════════════════════════════
    # Tab 2: API Keys
    # ═══════════════════════════════════════════

    def _build_keys_tab(self):
        frame = ct.CTkFrame(self.content_frame, fg_color="transparent")
        self._tab_frames.append(frame)

        # 列表区（可滚动）
        self._keys_list_frame = ct.CTkScrollableFrame(frame, fg_color="transparent")
        self._keys_list_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        # 底部按钮
        btn_row = ct.CTkFrame(frame, fg_color=DARK_BG, height=50)
        btn_row.pack(fill="x", side="bottom", padx=10, pady=(0, 10))

        ct.CTkButton(
            btn_row, text="＋ 添加 Provider", width=160, height=36,
            font=ct.CTkFont(size=13, weight="bold"),
            fg_color=CYAN, text_color="#000000", hover_color="#22D3EE",
            command=self._add_provider,
        ).pack(side="left", padx=4, pady=8)

        self._refresh_keys_list()

    def _refresh_keys_list(self):
        """刷新 Provider 列表"""
        for w in self._keys_list_frame.winfo_children():
            w.destroy()

        providers = self.config.get("providers", [])
        if not providers:
            ct.CTkLabel(
                self._keys_list_frame,
                text="暂无 Provider\n\n点击下方「＋ 添加 Provider」开始配置",
                font=ct.CTkFont(size=14), text_color="#64748b",
            ).pack(expand=True, pady=60)
            return

        for p in providers:
            self._make_provider_row(p)

    def _make_provider_row(self, provider: dict):
        row = ct.CTkFrame(self._keys_list_frame, fg_color=CARD_BG, corner_radius=8, height=64)
        row.pack(fill="x", pady=3)
        row.pack_propagate(False)

        # 名称
        ct.CTkLabel(
            row, text=provider.get("name", "?"),
            font=ct.CTkFont(size=14, weight="bold"),
        ).place(x=14, y=10)

        # Base URL
        ct.CTkLabel(
            row, text=provider.get("baseUrl", ""),
            font=ct.CTkFont(size=11), text_color="#94a3b8",
        ).place(x=14, y=34)

        # API Key（脱敏）
        from config_manager import mask_api_key
        masked = mask_api_key(provider.get("apiKey", ""))
        key_text = f"Key: {masked}" if masked else "Key: 未配置"
        ct.CTkLabel(
            row, text=key_text,
            font=ct.CTkFont(size=11), text_color="#94a3b8",
        ).place(x=340, y=22)

        # 模型列表
        models = provider.get("models", "")
        ct.CTkLabel(
            row, text=f"模型: {models}" if models else "模型: -",
            font=ct.CTkFont(size=11), text_color="#94a3b8",
        ).place(x=500, y=22)

        # 编辑按钮
        ct.CTkButton(
            row, text="✎", width=32, height=28,
            fg_color="transparent", hover_color="#334155",
            command=lambda p=provider: self._edit_provider(p),
        ).place(x=710, y=18)

        # 删除按钮
        ct.CTkButton(
            row, text="✕", width=32, height=28,
            fg_color="transparent", hover_color="#7F1D1D",
            text_color=RED,
            command=lambda p=provider: self._delete_provider(p),
        ).place(x=750, y=18)

    def _add_provider(self):
        self._open_provider_form(None)

    def _edit_provider(self, provider: dict):
        self._open_provider_form(provider)

    def _delete_provider(self, provider: dict):
        if not messagebox.askyesno("确认删除", f"确定要删除 Provider「{provider['name']}」吗？"):
            return
        self.config["providers"] = [p for p in self.config.get("providers", []) if p["id"] != provider["id"]]
        from config_manager import save_config
        save_config(self.config, self.config_path)
        self._refresh_keys_list()
        self._refresh_rules_list()
        self._update_stats()
        self._refresh_provider_switches()

    def _open_provider_form(self, provider: dict | None):
        """添加/编辑 Provider 模态窗口"""
        is_edit = provider is not None
        dialog = ct.CTkToplevel(self.window)
        dialog.title("编辑 Provider" if is_edit else "添加 Provider")
        dialog.geometry("460x400")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.configure(fg_color=DARK_BG)
        self._center_dialog(dialog, 460, 400)

        # 表单
        fields = {}
        y = 20

        for label, key, show in [
            ("名称", "name", False),
            ("Base URL", "baseUrl", False),
            ("API Key", "apiKey", True),
            ("模型列表（逗号分隔）", "models", False),
        ]:
            ct.CTkLabel(dialog, text=label, font=ct.CTkFont(size=12)).place(x=30, y=y)
            entry = ct.CTkEntry(dialog, width=390, show="●" if show else "")
            entry.place(x=30, y=y + 24)
            if provider:
                entry.insert(0, provider.get(key, ""))
            fields[key] = entry
            y += 70

        def save():
            data = {k: v.get().strip() for k, v in fields.items()}
            if not data["name"]:
                messagebox.showwarning("提示", "名称不能为空", parent=dialog)
                return

            if is_edit:
                provider.update(data)
            else:
                import time
                data["id"] = f"p-{int(time.time()*1000)}"
                self.config.setdefault("providers", []).append(data)

            from config_manager import save_config
            save_config(self.config, self.config_path)
            self._refresh_keys_list()
            self._refresh_rules_list()
            self._update_stats()
            self._refresh_provider_switches()
            dialog.destroy()

        ct.CTkButton(
            dialog, text="保存", width=100, height=34,
            fg_color=CYAN, text_color="#000000", font=ct.CTkFont(size=13, weight="bold"),
            command=save,
        ).place(x=170, y=340)
        ct.CTkButton(
            dialog, text="取消", width=80, height=34,
            fg_color="transparent", border_width=1, border_color="#475569",
            command=dialog.destroy,
        ).place(x=290, y=340)

    # ═══════════════════════════════════════════
    # Tab 3: 路由规则
    # ═══════════════════════════════════════════

    def _build_rules_tab(self):
        frame = ct.CTkFrame(self.content_frame, fg_color="transparent")
        self._tab_frames.append(frame)

        self._rules_list_frame = ct.CTkScrollableFrame(frame, fg_color="transparent")
        self._rules_list_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        btn_row = ct.CTkFrame(frame, fg_color=DARK_BG, height=50)
        btn_row.pack(fill="x", side="bottom", padx=10, pady=(0, 10))

        ct.CTkButton(
            btn_row, text="＋ 添加规则", width=160, height=36,
            font=ct.CTkFont(size=13, weight="bold"),
            fg_color=CYAN, text_color="#000000", hover_color="#22D3EE",
            command=self._add_rule,
        ).pack(side="left", padx=4, pady=8)

        self._refresh_rules_list()

    def _refresh_rules_list(self):
        for w in self._rules_list_frame.winfo_children():
            w.destroy()

        rules = self.config.get("rules", [])
        for i, rule in enumerate(rules):
            self._make_rule_row(rule, i, len(rules))

    def _make_rule_row(self, rule: dict, index: int, total: int):
        is_default = rule.get("id") == "default"
        row = ct.CTkFrame(self._rules_list_frame, fg_color=CARD_BG, corner_radius=8, height=64)
        row.pack(fill="x", pady=3)
        row.pack_propagate(False)

        # 优先级标签
        ct.CTkLabel(
            row, text=f"#{index + 1}",
            font=ct.CTkFont(size=11), text_color="#94a3b8",
        ).place(x=10, y=22)

        # 名称
        ct.CTkLabel(
            row, text=rule.get("name", "?"),
            font=ct.CTkFont(size=14, weight="bold"),
        ).place(x=44, y=10)

        # 匹配模式 → Provider
        from config_manager import get_provider
        prov = get_provider(self.config, rule.get("providerId", ""))
        prov_name = prov["name"] if prov else "未选择"
        pattern = rule.get("modelPattern", "*")
        override = f" → {rule['modelOverride']}" if rule.get("modelOverride") else ""
        ct.CTkLabel(
            row, text=f"{pattern}  →  {prov_name}{override}",
            font=ct.CTkFont(size=11), text_color="#94a3b8",
        ).place(x=44, y=34)

        btn_x = 680

        # 上移 / 下移
        if index > 0:
            ct.CTkButton(
                row, text="↑", width=28, height=26,
                fg_color="transparent", hover_color="#334155",
                command=lambda r=rule: self._move_rule(r, -1),
            ).place(x=btn_x, y=19)
            btn_x += 34

        if index < total - 1 and not is_default:
            ct.CTkButton(
                row, text="↓", width=28, height=26,
                fg_color="transparent", hover_color="#334155",
                command=lambda r=rule: self._move_rule(r, 1),
            ).place(x=btn_x, y=19)
            btn_x += 34

        # 编辑
        if not is_default:
            ct.CTkButton(
                row, text="✎", width=32, height=28,
                fg_color="transparent", hover_color="#334155",
                command=lambda r=rule: self._edit_rule(r),
            ).place(x=btn_x, y=19)
            btn_x += 40

        # 删除
        if not is_default:
            ct.CTkButton(
                row, text="✕", width=32, height=28,
                fg_color="transparent", hover_color="#7F1D1D",
                text_color=RED,
                command=lambda r=rule: self._delete_rule(r),
            ).place(x=btn_x, y=19)

    def _move_rule(self, rule: dict, direction: int):
        rules = self.config.get("rules", [])
        idx = next((i for i, r in enumerate(rules) if r["id"] == rule["id"]), -1)
        if idx < 0:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(rules):
            return
        rules[idx], rules[new_idx] = rules[new_idx], rules[idx]
        from config_manager import save_config
        save_config(self.config, self.config_path)
        self._refresh_rules_list()

    def _add_rule(self):
        self._open_rule_form(None)

    def _edit_rule(self, rule: dict):
        self._open_rule_form(rule)

    def _delete_rule(self, rule: dict):
        if not messagebox.askyesno("确认删除", f"确定要删除规则「{rule['name']}」吗？"):
            return
        self.config["rules"] = [r for r in self.config.get("rules", []) if r["id"] != rule["id"]]
        from config_manager import save_config
        save_config(self.config, self.config_path)
        self._refresh_rules_list()
        self._update_stats()

    def _open_rule_form(self, rule: dict | None):
        is_edit = rule is not None
        dialog = ct.CTkToplevel(self.window)
        dialog.title("编辑规则" if is_edit else "添加规则")
        dialog.geometry("460x380")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.configure(fg_color=DARK_BG)
        self._center_dialog(dialog, 460, 380)

        ct.CTkLabel(dialog, text="规则名称", font=ct.CTkFont(size=12)).place(x=30, y=20)
        name_entry = ct.CTkEntry(dialog, width=390)
        name_entry.place(x=30, y=44)
        if rule:
            name_entry.insert(0, rule.get("name", ""))

        ct.CTkLabel(dialog, text="模型匹配模式（支持 * 通配符，如 gpt-4o*）", font=ct.CTkFont(size=12)).place(x=30, y=82)
        pattern_entry = ct.CTkEntry(dialog, width=390)
        pattern_entry.place(x=30, y=106)
        if rule:
            pattern_entry.insert(0, rule.get("modelPattern", ""))

        ct.CTkLabel(dialog, text="目标 Provider", font=ct.CTkFont(size=12)).place(x=30, y=148)
        providers = self.config.get("providers", [])
        prov_names = [p["name"] for p in providers]
        prov_var = ct.StringVar(value=prov_names[0] if prov_names else "")
        prov_dropdown = ct.CTkOptionMenu(dialog, width=390, variable=prov_var, values=prov_names)
        prov_dropdown.place(x=30, y=172)
        if rule and providers:
            prov = next((p for p in providers if p["id"] == rule.get("providerId")), None)
            if prov:
                prov_var.set(prov["name"])

        ct.CTkLabel(dialog, text="模型名覆盖（可选，留空使用原始模型名）", font=ct.CTkFont(size=12)).place(x=30, y=218)
        override_entry = ct.CTkEntry(dialog, width=390)
        override_entry.place(x=30, y=242)
        if rule:
            override_entry.insert(0, rule.get("modelOverride", ""))

        def save():
            name = name_entry.get().strip()
            pattern = pattern_entry.get().strip()
            if not name or not pattern:
                messagebox.showwarning("提示", "规则名称和匹配模式不能为空", parent=dialog)
                return

            prov_name = prov_var.get()
            prov_id = ""
            for p in providers:
                if p["name"] == prov_name:
                    prov_id = p["id"]
                    break

            data = {
                "name": name,
                "modelPattern": pattern,
                "providerId": prov_id,
                "modelOverride": override_entry.get().strip(),
            }

            if is_edit:
                rule.update(data)
            else:
                import time
                data["id"] = f"r-{int(time.time()*1000)}"
                self.config.setdefault("rules", []).append(data)

            from config_manager import save_config
            save_config(self.config, self.config_path)
            self._refresh_rules_list()
            self._update_stats()
            dialog.destroy()

        ct.CTkButton(
            dialog, text="保存", width=100, height=34,
            fg_color=CYAN, text_color="#000000", font=ct.CTkFont(size=13, weight="bold"),
            command=save,
        ).place(x=170, y=310)
        ct.CTkButton(
            dialog, text="取消", width=80, height=34,
            fg_color="transparent", border_width=1, border_color="#475569",
            command=dialog.destroy,
        ).place(x=290, y=310)

    # ═══════════════════════════════════════════
    # Tab 4: 请求日志
    # ═══════════════════════════════════════════

    def _build_logs_tab(self):
        frame = ct.CTkFrame(self.content_frame, fg_color="transparent")
        self._tab_frames.append(frame)

        # 工具栏
        toolbar = ct.CTkFrame(frame, fg_color=DARK_BG, height=40)
        toolbar.pack(fill="x", padx=0, pady=(0, 4))

        ct.CTkButton(
            toolbar, text="清空日志", width=100, height=30,
            fg_color=CARD_BG, hover_color="#334155",
            command=self._clear_logs,
        ).pack(side="right", padx=10, pady=5)

        # 日志列表
        self._logs_list_frame = ct.CTkScrollableFrame(frame, fg_color="transparent")
        self._logs_list_frame.pack(fill="both", expand=True, padx=4, pady=2)
        self._logs_list_frame.pack_propagate(False)

        self._logs_empty_label = ct.CTkLabel(
            self._logs_list_frame,
            text="暂无请求日志",
            font=ct.CTkFont(size=14), text_color="#64748b",
        )

    def _clear_logs(self):
        self._logs = []
        self._refresh_logs()

    def _refresh_logs(self):
        """刷新日志列表"""
        for w in self._logs_list_frame.winfo_children():
            w.destroy()

        if not self._logs:
            self._logs_empty_label = ct.CTkLabel(
                self._logs_list_frame,
                text="暂无请求日志",
                font=ct.CTkFont(size=14), text_color="#64748b",
            )
            self._logs_empty_label.pack(expand=True, pady=40)
            return

        for log in reversed(self._logs[-200:]):  # 显示最近200条
            status = log.get("status", 0)
            if 200 <= status < 300:
                color = GREEN
            elif 400 <= status < 500:
                color = ORANGE
            elif status >= 500:
                color = RED
            else:
                color = "#ffffff"

            line = f"[{log['time']}]  {log['model']}  →  {log['rule']}  |  {log['ua'][:30]}  |  "
            row = ct.CTkFrame(self._logs_list_frame, fg_color="transparent", height=26)
            row.pack(fill="x", pady=1)

            ct.CTkLabel(
                row, text=line,
                font=ct.CTkFont(size=11, family="Consolas"), text_color="#94a3b8",
            ).pack(side="left")

            ct.CTkLabel(
                row, text=str(status),
                font=ct.CTkFont(size=11, family="Consolas", weight="bold"), text_color=color,
            ).pack(side="left")

        # 自动滚动到底部
        self._logs_list_frame._parent_canvas.yview_moveto(1.0)

    # ═══════════════════════════════════════════
    # 代理控制
    # ═══════════════════════════════════════════

    def _toggle_proxy(self):
        if self._proxy_running:
            self._stop_proxy()
        else:
            self._start_proxy()

    def _start_proxy(self):
        try:
            port = int(self._port_var.get())
        except ValueError:
            messagebox.showwarning("提示", "端口号必须是数字")
            return

        self.config["proxyPort"] = port
        from config_manager import save_config
        save_config(self.config, self.config_path)

        self._on_start_proxy(port)
        self._proxy_running = True
        self._start_time = time.time()

        # 更新 UI
        self._status_canvas.itemconfig(self._status_dot, fill=GREEN)
        self._status_label.configure(text="代理运行中")
        self._toggle_btn.configure(text="■  停止代理", fg_color=RED, hover_color="#DC2626")
        self._card_address._value_label.configure(text=f"http://127.0.0.1:{port}")

        # 更新托盘菜单
        if self._tray_icon:
            self._tray_icon.set_proxy_status(True)

        self._start_runtime_timer()

    def _stop_proxy(self):
        self._on_stop_proxy()
        self._proxy_running = False
        self._start_time = None

        self._status_canvas.itemconfig(self._status_dot, fill=RED)
        self._status_label.configure(text="代理已停止")
        self._toggle_btn.configure(text="▶  启动代理", fg_color=GREEN, hover_color="#16A34A")

        if self._tray_icon:
            self._tray_icon.set_proxy_status(False)

        if self._runtime_timer_id:
            self.window.after_cancel(self._runtime_timer_id)
            self._runtime_timer_id = None

    def _start_runtime_timer(self):
        """每 60 秒更新一次运行时间"""
        self._update_runtime()
        self._runtime_timer_id = self.window.after(60000, self._start_runtime_timer)

    def _update_runtime(self):
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            self._card_runtime._value_label.configure(text=f"{h:02d}小时{m:02d}分")
        self._update_stats()

    def _update_stats(self):
        rules_count = len(self.config.get("rules", []))
        self._card_rules._value_label.configure(text=str(rules_count))
        self._card_requests._value_label.configure(text=str(len(self._logs)))

    # ═══════════════════════════════════════════
    # 日志轮询
    # ═══════════════════════════════════════════

    def _poll_logs(self):
        """每 200ms 从队列拉取日志"""
        try:
            while True:
                entry = self.log_queue.get_nowait()
                self._logs.append(entry)
                # 限制最多 500 条
                if len(self._logs) > 500:
                    self._logs = self._logs[-500:]
        except queue.Empty:
            pass

        # 如果当前在日志 tab，刷新显示
        if getattr(self, "_current_tab", 0) == 3:
            self._refresh_logs()

        self._update_stats()
        self.window.after(200, self._poll_logs)

    # ═══════════════════════════════════════════
    # 工具函数
    # ═══════════════════════════════════════════

    def _center_dialog(self, dialog: ct.CTkToplevel, w: int, h: int):
        dialog.update_idletasks()
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    # ═══════════════════════════════════════════
    # 快速接入 AI 工具
    # ═══════════════════════════════════════════

    def _refresh_provider_switches(self):
        """刷新 Provider 开关按钮 — 每个 Provider 一个开关"""
        for w in self._provider_switch_frame.winfo_children():
            w.destroy()
        self._provider_switches.clear()

        providers = self.config.get("providers", [])
        # 找出当前默认路由指向的 provider
        default_prov_id = None
        for r in self.config.get("rules", []):
            if r.get("id") == "default":
                default_prov_id = r.get("providerId")
                break

        for p in providers:
            prov_id = p["id"]
            is_active = (prov_id == default_prov_id)
            name = p.get("name", "?")
            # 提取简短显示名（取第一个单词或前4个字符）
            display = name if len(name) <= 6 else name[:5] + "…"

            fg = CYAN if is_active else "#334155"
            text_col = "#000000" if is_active else "#94a3b8"

            btn = ct.CTkButton(
                self._provider_switch_frame,
                text=display,
                width=82, height=28,
                font=ct.CTkFont(size=11, weight="bold"),
                fg_color=fg, text_color=text_col,
                hover_color="#0F3460",
                command=lambda pid=prov_id: self._switch_provider(pid),
            )
            btn.pack(side="left", padx=2)
            self._provider_switches[prov_id] = btn

            if is_active:
                self._active_provider_id = prov_id
                self._tooltip_text = name

    def _switch_provider(self, prov_id: str):
        """点击 Provider 开关 → 切换默认路由 → 写入 Codex 配置"""
        if prov_id == self._active_provider_id:
            return  # 已经是激活的

        # 更新默认路由的 providerId
        for r in self.config.get("rules", []):
            if r.get("id") == "default":
                r["providerId"] = prov_id
                break

        from config_manager import save_config, get_provider
        save_config(self.config, self.config_path)

        self._active_provider_id = prov_id
        self._refresh_provider_switches()

        # 自动写入 Codex 配置
        prov = get_provider(self.config, prov_id)
        if prov:
            model = prov.get("models", "").split(",")[0].strip()
            self._write_tool_config(prov, model)

    def _write_tool_config(self, prov: dict, model: str):
        """写入 AI 工具配置并显示结果"""
        port = self.config.get("proxyPort", 3456)
        tool_choice = self._tool_var.get()
        prov_name = prov.get("name", "?")

        from tool_configurator import configure_codex, configure_claude_code
        results = {}
        if "Codex" in tool_choice:
            results["Codex"] = configure_codex(port, prov_name, model)
        if "Claude" in tool_choice:
            results["Claude Code"] = configure_claude_code(port, prov_name, haiku_model=model, sonnet_model=model)

        ok = [k for k, v in results.items() if v]
        fail = [k for k, v in results.items() if not v]

        if not ok:
            self._quick_status.configure(text=" | ".join(fail), text_color=RED)
        elif not self._proxy_running:
            self._quick_status.configure(
                text=f"✓ {prov_name} · {model}  |  请先启动代理！", text_color=ORANGE
            )
        else:
            self._quick_status.configure(
                text=f"✓ {prov_name} · {model}", text_color=GREEN
            )

    def _quick_configure(self):
        """手动点击「写入配置」—— 用当前激活的 Provider 重写工具配置"""
        if not self._active_provider_id:
            messagebox.showwarning("提示", "请先在底部点击一个 Provider 开关")
            return
        from config_manager import get_provider
        prov = get_provider(self.config, self._active_provider_id)
        if not prov:
            return
        model = prov.get("models", "").split(",")[0].strip()
        self._write_tool_config(prov, model)

    def run(self):
        """启动 GUI 主循环"""
        self.window.mainloop()
