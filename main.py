"""
CCSwitch — AI 编码代理桌面工具
入口文件，负责启动 GUI、代理服务器和系统托盘
"""

import os
import sys
import queue
import ctypes

from icon_generator import generate_icons
from config_manager import load_config, save_config
from proxy_server import ProxyServer
from tray_icon import TrayIcon
from gui_app import CCSwitchApp


def get_data_dir():
    """获取数据目录（配置、图标存放位置）"""
    if getattr(sys, "frozen", False):
        # 打包后的 exe：使用 %APPDATA%/CCSwitch
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        data_dir = os.path.join(appdata, "CCSwitch")
    else:
        # 源码运行：使用脚本同目录
        data_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def main():
    data_dir = get_data_dir()

    # ── 生成图标（如果不存在）──
    icon_path = os.path.join(data_dir, "icon.png")
    if not os.path.exists(icon_path):
        generate_icons(data_dir)

    # ── 加载配置 ──
    config_path = os.path.join(data_dir, "config.json")
    config = load_config(config_path)
    # 首次启动立即保存默认配置
    if not os.path.exists(config_path):
        save_config(config, config_path)

    # ── 配置引用 ──
    config_ref = [config]

    def get_config():
        return config_ref[0]

    # ── 日志队列 ──
    log_queue = queue.Queue(maxsize=1000)

    # ── 代理服务器 ──
    proxy_ref = [ProxyServer(get_config, log_queue)]

    # ── 懒引用容器（解决循环依赖）──
    tray_ref = [None]
    app_ref = [None]

    # ── 回调定义 ──
    def on_tray_show():
        if app_ref[0]:
            app_ref[0].show_window()

    def on_tray_start_proxy():
        if app_ref[0] and not app_ref[0]._proxy_running:
            app_ref[0]._start_proxy()

    def on_tray_stop_proxy():
        if app_ref[0] and app_ref[0]._proxy_running:
            app_ref[0]._stop_proxy()

    def on_exit():
        proxy_ref[0].stop()
        cfg = config_ref[0]
        if app_ref[0]:
            try:
                cfg["proxyPort"] = int(app_ref[0]._port_var.get())
            except (ValueError, AttributeError):
                pass
        save_config(cfg, config_path)
        if tray_ref[0]:
            tray_ref[0].stop()
        os._exit(0)

    def gui_start_proxy(port: int):
        proxy_ref[0].stop()
        proxy_ref[0] = ProxyServer(get_config, log_queue)
        proxy_ref[0].start(port)

    def gui_stop_proxy():
        proxy_ref[0].stop()

    # ── 创建托盘 ──
    tray = TrayIcon(
        icon_path=icon_path,
        on_show=on_tray_show,
        on_start_proxy=on_tray_start_proxy,
        on_stop_proxy=on_tray_stop_proxy,
        on_exit=on_exit,
    )
    tray_ref[0] = tray

    # ── 创建 GUI ──
    app = CCSwitchApp(
        config=config,
        config_path=config_path,
        log_queue=log_queue,
        on_start_proxy=gui_start_proxy,
        on_stop_proxy=gui_stop_proxy,
        on_exit=on_exit,
        tray_icon=tray,
    )
    app_ref[0] = app

    # ── 启动托盘 ──
    tray.start()

    # ── Windows 任务栏图标 ──
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CCSwitch.AIProxy")
        except Exception:
            pass

    # ── 启动 GUI 主循环 ──
    app.run()


if __name__ == "__main__":
    main()
