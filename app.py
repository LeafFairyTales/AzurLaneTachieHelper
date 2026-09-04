import ctypes
import locale
import os
import subprocess
import sys
from ast import literal_eval

# QtWebEngine：无 GPU 环境（VDI）启用 SwiftShader 软件渲染 WebGL，Live2D 预览依赖。
# 必须在 QApplication 创建前设置。
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--enable-unsafe-swiftshader --use-angle=swiftshader-webgl --ignore-gpu-blocklist",
)

import qdarktheme
import UnityPy.config
from PySide6.QtCore import QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from src.shell import ModuleShell
from src.utility import resource_path

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.62f3"

NOTICE_TEXT = (
    "本项目基于开源项目 AzurLaneTachieHelper 修改优化，由 @LeafFairyTales 完善。\n"
    "源地址：https://github.com/MuteApo/AzurLaneTachieHelper\n"
    "本工具仅供学习交流使用，请勿传播或用于商业用途。"
)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("cheshire.ico")))
    qdarktheme.setup_theme("auto")

    if sys.platform == "win32":
        code = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        lang = locale.windows_locale[code]
    elif sys.platform == "darwin":
        cmd = ["defaults", "read", "-g", "AppleLanguages"]
        output = subprocess.check_output(cmd, text=True)
        lang = literal_eval(output)[0]
        if lang == "zh-Hans-CN":
            lang = "zh_CN"
    else:
        lang = locale.getlocale()[0]

    path = os.path.join("i18n", f"{lang}.qm")
    if os.path.exists(path):
        trans = QTranslator(app)
        trans.load(path)
        app.installTranslator(trans)

    # 启动确认：版权与使用声明
    box = QMessageBox()
    box.setWindowTitle("AzurLane Tachie Helper")
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(NOTICE_TEXT)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()

    win = ModuleShell()
    win.show()

    sys.exit(app.exec())
