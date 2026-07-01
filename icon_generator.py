"""
CCSwitch 图标生成器
从用户提供的图片生成 icon.png 和 icon.ico
"""

from PIL import Image
import os


def generate_icons(output_dir: str = "."):
    """从 custom_icon.png 生成 icon.png (256x256) 和 icon.ico"""
    size = 256

    custom_path = os.path.join(output_dir, "custom_icon.png")
    if os.path.exists(custom_path):
        img = Image.open(custom_path)
    else:
        # 备选：从同目录查找
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_icon.png")
        if os.path.exists(alt):
            img = Image.open(alt)
        else:
            raise FileNotFoundError("custom_icon.png not found")

    # 统一为 256×256 RGBA
    img = img.convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)

    # 保存 PNG
    png_path = os.path.join(output_dir, "icon.png")
    img.save(png_path)

    # 保存 ICO
    ico_path = os.path.join(output_dir, "icon.ico")
    img.save(ico_path, format="ICO", sizes=[(size, size)])

    print(f"Icons generated: {png_path}, {ico_path}")
    return png_path, ico_path


if __name__ == "__main__":
    generate_icons(os.path.dirname(os.path.abspath(__file__)))
