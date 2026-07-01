"""
CCSwitch 打包脚本
使用 PyInstaller 将项目打包为单文件 Windows 可执行程序
"""

import os
import sys
import subprocess


def build():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    # 确保图标存在
    icon_path = os.path.join(base_dir, "icon.ico")
    if not os.path.exists(icon_path):
        print("图标文件 icon.ico 不存在，正在生成...")
        from icon_generator import generate_icons
        generate_icons(base_dir)

    # PyInstaller 命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--icon=icon.ico",
        "--name", "CCSwitch",
        "--add-data", f"icon.png{os.pathsep}.",
        "--add-data", f"icon.ico{os.pathsep}.",
        "--hidden-import", "customtkinter",
        "--hidden-import", "pystray",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "flask",
        "--hidden-import", "werkzeug",
        "--hidden-import", "requests",
        "--collect-all", "customtkinter",
        "main.py",
    ]

    print("=" * 60)
    print("CCSwitch 打包脚本")
    print("=" * 60)
    print(f"执行命令: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=base_dir)

    if result.returncode == 0:
        exe_path = os.path.join(base_dir, "dist", "CCSwitch.exe")
        print()
        print("=" * 60)
        print(f"✓ 打包成功！")
        print(f"  输出文件: {exe_path}")
        print(f"  文件大小: {os.path.getsize(exe_path) / (1024*1024):.1f} MB")
        print("=" * 60)
    else:
        print()
        print("✗ 打包失败，请检查错误信息")
        sys.exit(1)


if __name__ == "__main__":
    build()
