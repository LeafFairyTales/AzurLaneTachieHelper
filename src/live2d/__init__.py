"""Live2D 功能模块。

新架构规范落地示例：
- 模块 = 独立包 src/live2d/，自持工具条 / 内容区 / 状态行；
- 只 import 公共层（..logger / ..module_registry 等）与包内子模块，不引用其它模块；
- 业务能力需要共享时下沉公共层。

当前能力：加载 Live2D bundle（moc3 + 贴图）→ 本地页面实时预览（物理/呼吸/拖拽）。
动作预览（AnimationClip → motion3.json 转换）与 PSD 导出/导入在后续迭代。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..logger import logger
from ..module_registry import Module, register
from .helper import Live2DHelper
from .preview import Live2DPreview


@register
class Live2DModule(Module):
    name = "Live2D"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_dir: str | None = None
        self.model3_name: str | None = None
        self.motion_names: list[str] = []

        self._init_toolbar()
        self._init_body()
        self._init_status()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.toolbar_widget)
        root.addWidget(self.body, 1)
        root.addWidget(self.status_widget)

    # --- 工具条（模块自持功能入口） ---
    def _init_toolbar(self):
        row = QHBoxLayout()
        row.setContentsMargins(6, 4, 6, 2)

        self.btn_open = QPushButton(self.tr("Open Live2D Bundle"))
        self.btn_open.clicked.connect(self.on_open_bundle)

        # 动作列表：动作多时滚动浏览，单击播放（默认自动播 idle）
        self.list_motions = QListWidget()
        self.list_motions.setFixedWidth(180)
        self.list_motions.setMinimumHeight(120)
        self.list_motions.itemClicked.connect(self.on_motion_clicked)

        row.addWidget(self.btn_open)
        row.addWidget(self.list_motions, 1)
        row.addStretch(0)
        self.toolbar_widget = QWidget()
        self.toolbar_widget.setLayout(row)

    # --- 内容区：占位提示 / 预览视图 ---
    def _init_body(self):
        self.lbl_placeholder = QLabel(self.tr("Open a Live2D bundle to preview"))
        self.lbl_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_placeholder.setWordWrap(True)

        self.preview = Live2DPreview(self)

        self.body = QStackedWidget()
        self.body.addWidget(self.lbl_placeholder)
        self.body.addWidget(self.preview)

    # --- 状态行 ---
    def _init_status(self):
        self.lbl_status = QLabel(self.tr("Ready"))
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 2, 6, 2)
        bar.addWidget(self.lbl_status, 1)
        self.status_widget = QWidget()
        self.status_widget.setLayout(bar)

    def _status(self, text: str):
        self.lbl_status.setText(text)

    # --- 动作 ---
    def on_open_bundle(self):
        last = ""
        file, _ = QFileDialog.getOpenFileName(self, self.tr("Select Live2D Bundle"), last)
        if not file:
            return
        self._status(self.tr("Extracting") + f" {os.path.basename(file)} ...")
        try:
            bundle = Live2DHelper.extract(file)
            model_dir, model3 = Live2DHelper.materialize(bundle)
            self.motion_names = Live2DHelper.with_motions(model_dir, model3, file)
            Live2DHelper.prepare_web(model_dir, model3)
        except Exception as e:  # noqa: BLE001 —— 解包失败仅提示，不影响模块/宿主
            logger.exception("Live2D extract failed")
            QMessageBox.warning(self, self.tr("Live2D"), self.tr("Failed") + f": {e}")
            self._status(self.tr("Failed") + f": {e}")
            return

        if self.model_dir:  # 清理上一个解包目录
            Live2DHelper.cleanup(self.model_dir)
        self.model_dir = model_dir
        self.model3_name = model3

        self._refresh_motions()
        self.preview.show_model(model_dir)
        self.body.setCurrentWidget(self.preview)
        self._status(
            self.tr("Loaded") + f": {bundle.name} ({len(bundle.textures)} "
            + self.tr("textures") + f", {len(self.motion_names)} " + self.tr("motions") + ")"
        )
        logger.info(
            "Live2D loaded: %s (%d textures, %d motions)",
            bundle.name, len(bundle.textures), len(self.motion_names),
        )

    def _refresh_motions(self):
        """填充动作列表；默认模型就绪后由页面自动播 idle。"""
        self.list_motions.clear()
        for name in self.motion_names:
            self.list_motions.addItem(name)

    def on_motion_clicked(self, item):
        name = item.text()
        self.preview.view.page().runJavaScript(f'window.playMotion("{name}")')
        self._status(self.tr("Motion") + f": {name}")