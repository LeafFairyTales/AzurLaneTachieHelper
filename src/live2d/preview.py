"""Live2D 预览视图：本地 HTTP 服务托管模型目录 + QWebEngineView 渲染。

页面（index.html）与模型同目录，经 127.0.0.1 随机端口为同源加载，
pixi-live2d-display 的 fetch / 贴图 / moc3 全部走标准 http，无 file:// 限制。
"""
import functools
import http.server
import threading

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默，避免刷屏
        pass


class Live2DPreview(QWidget):
    """模型预览视图：show_model() 后由浏览器渲染 Live2D。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = QWebEngineView(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def show_model(self, model_dir: str):
        self.clear()
        handler = functools.partial(_Handler, directory=model_dir)
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        port = self._server.server_address[1]
        self.view.setUrl(QUrl(f"http://127.0.0.1:{port}/index.html"))

    def clear(self):
        if self._server is not None:
            self._server.shutdown()
            if self._thread is not None:
                self._thread.join(timeout=2)
            self._server.server_close()
            self._server = None
            self._thread = None