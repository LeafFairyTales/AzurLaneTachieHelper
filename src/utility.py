import os
import sys

from PIL import Image


def resource_path(relative: str) -> str:
    """返回资源文件的绝对路径：PyInstaller 打包后指向 _MEIPASS，开发时相对当前目录。"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative)


def exists(v):
    return v is not None


def default(v, d):
    return v if exists(v) else d


def check_and_save(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def open_and_transpose(path: str) -> Image.Image:
    return Image.open(path).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
