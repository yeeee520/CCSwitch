"""
CCSwitch 系统托盘图标管理
使用 pystray + PIL 图标，双击显示/隐藏窗口，右键菜单操作
"""

import threading
import pystray
from PIL import Image


class TrayIcon:
    """系统托盘图标管理"""

    def __init__(self, icon_path: str, on_show, on_start_proxy, on_stop_proxy, on_exit):
        """
        on_show:      回调 → 显示/置顶主窗口
        on_start_proxy: 回调 → 启动代理
        on_stop_proxy:  回调 → 停止代理
        on_exit:     回调 → 退出程序
        """
        self.icon_path = icon_path
        self._on_show = on_show
        self._on_start_proxy = on_start_proxy
        self._on_stop_proxy = on_stop_proxy
        self._on_exit = on_exit
        self._tray: pystray.Icon | None = None
        self._thread: threading.Thread | None = None
        self._proxy_running = False

    def set_proxy_status(self, running: bool):
        """更新代理状态（影响右键菜单文字）"""
        self._proxy_running = running
        if self._tray:
            self._tray.update_menu()

    def _build_menu(self):
        """构建右键菜单"""
        proxy_action = (
            pystray.MenuItem("停止代理", self._on_stop_proxy)
            if self._proxy_running
            else pystray.MenuItem("启动代理", self._on_start_proxy)
        )
        return pystray.Menu(
            pystray.MenuItem("显示窗口", self._on_show, default=True),
            proxy_action,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._on_exit),
        )

    def _run(self):
        """在独立线程中运行 pystray"""
        img = Image.open(self.icon_path)
        self._tray = pystray.Icon(
            "CCSwitch",
            img,
            "CCSwitch - AI 编码代理",
            menu=self._build_menu(),
        )
        self._tray.run()

    def start(self):
        """启动托盘线程"""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """停止托盘"""
        if self._tray:
            self._tray.stop()
            self._tray = None

    def notify(self, title: str, message: str):
        """弹出气泡通知"""
        if self._tray:
            self._tray.notify(message, title)
