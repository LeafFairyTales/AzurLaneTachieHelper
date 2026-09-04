"""ModuleShell：模块化宿主窗口。

布局：左侧导航列表（当前模块）+ 中央 QStackedWidget（各模块实例）。
- 模块加载：经 module_registry.load_all() 逐个 try import；实例化失败只跳过该模块
  并在宿主状态栏提示 —— 单个模块的问题不影响其它模块与宿主。
- 发布裁剪：环境变量 ALTH_EXCLUDE_MODULES（见 module_registry）。
- 菜单与状态栏不设全局栏 —— 各模块在自身内部自持功能 UI。
- 拖放：由各模块 widget 自行接收（setAcceptDrops），宿主不转发。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from . import module_registry
from .base import Config


class ModuleShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AzurLane Tachie Helper (Telegram @LeafFairyTales Edited)")
        self.resize(960, 540)

        Config.init()

        self.nav = QListWidget()
        self.nav.setMinimumWidth(80)
        self.nav.setMaximumWidth(360)
        self.stack = QStackedWidget()

        self.module_instances: list[module_registry.Module] = []
        skipped: list[str] = []
        for klass in module_registry.load_all():
            try:
                inst = klass(self)
            except Exception as e:  # noqa: BLE001 —— 模块级故障隔离点
                skipped.append(f"{klass.name} ({e!r})")
                continue
            self.module_instances.append(inst)
            self.stack.addWidget(inst)
            self.nav.addItem(self.tr(inst.name))

        if skipped:
            print("[ModuleShell] skipped modules:", skipped)
            self.statusBar().showMessage(self.tr("Module load failed") + ": " + "; ".join(skipped))

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([132, 828])  # 初始：导航 132 / 工作区余下
        splitter.setChildrenCollapsible(False)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        if self.module_instances:
            self.nav.setCurrentRow(0)
            self.stack.setCurrentIndex(0)