import os
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QDir, QObject, QThread, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .base import Config
from .base.Data import FaceModeType
from .base.Layer import prefered_layer
from .logger import logger
from .module.AssetManager import AssetManager
from .module.ImportHelper import ImportHelper
from .ui import Menu
from .ui.IconViewer import IconViewer
from .ui.Previewer import Previewer
from .ui.Table import IconTable, PaintingfaceTable, PaintingTable


class ImportWorker(QObject):
    """后台批量导入（不阻塞 GUI）。"""

    finished = Signal(dict)

    def __init__(self, meta_paths: list[str], face_mode: FaceModeType, from_export: bool):
        super().__init__()
        self.meta_paths = meta_paths
        self.face_mode = face_mode
        self.from_export = from_export

    def run(self):
        res = ImportHelper.run_many(self.meta_paths, self.face_mode, self.from_export)
        self.finished.emit(res)


class ExportWorker(QObject):
    """后台批量导出图层 PNG（不导入，供用户编辑后再 from-export 导入）。"""

    finished = Signal(dict)

    def __init__(self, meta_paths: list[str], face_mode: FaceModeType):
        super().__init__()
        self.meta_paths = meta_paths
        self.face_mode = face_mode

    def run(self):
        res = ImportHelper.export_many(self.meta_paths, self.face_mode)
        self.finished.emit(res)


class PsdImportWorker(QObject):
    """后台从 PSD 导入（PSD + 当前索引 -> 图层 -> repl -> encode）。"""

    finished = Signal(dict)

    def __init__(self, psd_path: str, meta_path: str, face_mode: FaceModeType):
        super().__init__()
        self.psd_path = psd_path
        self.meta_path = meta_path
        self.face_mode = face_mode

    def run(self):
        res = ImportHelper.import_psd(self.psd_path, self.meta_path, self.face_mode)
        self.finished.emit({os.path.basename(self.meta_path): res})


class AzurLaneTachieHelper(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tr("AzurLane Tachie Helper") + " (Telegram @LeafFairyTales Edited)")
        self.setAcceptDrops(True)
        self.resize(960, 540)

        Config.init()
        self.asset_manager = AssetManager()

        self.face_mode_map = {
            FaceModeType.Off: self.tr("Off"),
            FaceModeType.Auto: self.tr("Auto"),
            FaceModeType.Custom: self.tr("Custom"),
            FaceModeType.Full: self.tr("Full"),
        }
        self.server_map = {"CN": self.tr("CN"), "JP": self.tr("JP"), "EN": self.tr("EN")}

        self._init_statusbar()
        self._init_menu()
        self._init_ui()

    def _init_statusbar(self):
        self.msg_file = QLabel(self.tr("Ready"))
        self.msg_face_mode = QLabel()
        self.msg_server = QLabel()
        self.msg_skip_missing = QLabel()

        self.statusBar().addWidget(self.msg_file)
        self.statusBar().addPermanentWidget(self.msg_face_mode)
        self.statusBar().addPermanentWidget(self.msg_server)
        self.statusBar().addPermanentWidget(self.msg_skip_missing)

    def _init_ui(self):
        self.preview = Previewer(self._encode)
        self.tPainting = PaintingTable(self.preview)
        self.tFace = PaintingfaceTable(self.preview)
        self.tIcon = IconTable(self.preview)
        self.preview.set_callback(self.tPainting.load, self.tFace.load, self.tIcon.load)

        left = QVBoxLayout()
        left.addLayout(self.tPainting)
        left.addLayout(self.tFace)
        left.addLayout(self.tIcon)

        # 左列三张表共用一个滚动条：内容按行数全展开，窗口高度不足时整体滚动
        left_widget = QWidget()
        left_widget.setLayout(left)

        scroll = QScrollArea()
        scroll.setWidget(left_widget)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)

        layout = QHBoxLayout()
        layout.addWidget(scroll)
        layout.addWidget(sep)
        layout.addWidget(self.preview)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def _init_menu(self):
        # File：区域 1 打开文件 / 区域 2 PSD 相关 / 区域 3 普通流程（批量）
        self.mFile = Menu.File(
            self.onOpenMetadata,
            self.onDecodeToPsd,
            self.onImportPsd,
            self.onExportLayers,
            lambda: self.onImportBatch(True),   # Import From Images（用 export PNG）
            lambda: self.onImportBatch(False),  # Export && Import（内部合成）
        )
        self.mEdit = Menu.Edit(
            self.onEditClip,
            lambda: self.onEditClipIcon("shipyardicon"),
            lambda: self.onEditClipIcon("herohrzicon"),
            lambda: self.onEditClipIcon("squareicon"),
        )
        self.mOption = Menu.Option(self.refresh_statusbar, self.onToggleFaceMode)

        self.menuBar().addMenu(self.mFile)
        self.menuBar().addMenu(self.mEdit)
        self.menuBar().addMenu(self.mOption)

    def _start_import_worker(self, worker: ImportWorker):
        self.import_worker = worker
        self.import_thread = QThread(self)
        self.import_worker.moveToThread(self.import_thread)
        self.import_thread.started.connect(self.import_worker.run)
        self.import_worker.finished.connect(self.onImportDone)
        self.import_worker.finished.connect(self.import_thread.quit)
        self.import_worker.finished.connect(self.import_worker.deleteLater)
        self.import_thread.finished.connect(self.import_thread.deleteLater)
        self.import_thread.start()

    def _start_export_worker(self, worker: ExportWorker):
        self.export_worker = worker
        self.export_thread = QThread(self)
        self.export_worker.moveToThread(self.export_thread)
        self.export_thread.started.connect(self.export_worker.run)
        self.export_worker.finished.connect(self.onExportDone)
        self.export_worker.finished.connect(self.export_thread.quit)
        self.export_worker.finished.connect(self.export_worker.deleteLater)
        self.export_thread.finished.connect(self.export_thread.deleteLater)
        self.export_thread.start()

    def _start_psd_worker(self, worker: PsdImportWorker):
        self.psd_worker = worker
        self.psd_thread = QThread(self)
        self.psd_worker.moveToThread(self.psd_thread)
        self.psd_thread.started.connect(self.psd_worker.run)
        self.psd_worker.finished.connect(self.onImportDone)
        self.psd_worker.finished.connect(self.psd_thread.quit)
        self.psd_worker.finished.connect(self.psd_worker.deleteLater)
        self.psd_thread.finished.connect(self.psd_thread.deleteLater)
        self.psd_thread.start()

    def onImportBatch(self, from_export: bool):
        """选工作根目录，后台批量导入（任意目录结构，递归发现索引）。模式由 Option 全局设置决定。"""
        last = os.path.dirname(Config.get_recent_path()) if Config.get_recent_path() else os.getcwd()
        root = QFileDialog.getExistingDirectory(self, self.tr("Select Work Root"), last)
        if not root:
            return
        found = ImportHelper.discover_ships(root)  # [(name, meta_path)]
        if not found:
            QMessageBox.warning(self, self.tr("AzurLane Tachie Helper"), self.tr("No ships found in") + f"\n{root}")
            return
        face_mode = Config.get_face_mode()
        source = self.tr("Export PNGs") if from_export else self.tr("Internal")
        self.statusBar().showMessage(
            self.tr("Importing") + f" {len(found)} ships ({source}, {face_mode.name.lower()}) ..."
        )
        self._start_import_worker(ImportWorker([p for _, p in found], face_mode, from_export))

    def onImportDone(self, results: dict):
        total = sum(len(v) for v in results.values())
        fails = [k for k, v in results.items() if not v]
        msg = self.tr("Import done") + f": {total} " + self.tr("outputs")
        if fails:
            msg += "\n" + self.tr("Failed") + f": {', '.join(fails)}"
        self.statusBar().showMessage(msg)
        QMessageBox.information(self, self.tr("AzurLane Tachie Helper"), msg)

    def onExportLayers(self):
        """选工作根目录，后台批量导出图层 PNG（不导入）。模式由 Option 全局设置决定。"""
        last = os.path.dirname(Config.get_recent_path()) if Config.get_recent_path() else os.getcwd()
        root = QFileDialog.getExistingDirectory(self, self.tr("Select Work Root"), last)
        if not root:
            return
        found = ImportHelper.discover_ships(root)
        if not found:
            QMessageBox.warning(self, self.tr("AzurLane Tachie Helper"), self.tr("No ships found in") + f"\n{root}")
            return
        face_mode = Config.get_face_mode()
        self.statusBar().showMessage(self.tr("Exporting") + f" {len(found)} ships ({face_mode.name.lower()}) ...")
        self._start_export_worker(ExportWorker([p for _, p in found], face_mode))

    def onExportDone(self, results: dict):
        ok = [k for k, v in results.items() if v]
        fails = [k for k, v in results.items() if not v]
        msg = self.tr("Export done") + f": {len(ok)} " + self.tr("ships")
        if fails:
            msg += "\n" + self.tr("Failed") + f": {', '.join(fails)}"
        self.statusBar().showMessage(msg)
        QMessageBox.information(self, self.tr("AzurLane Tachie Helper"), msg)

    def onImportPsd(self):
        """从当前打开索引对应的解码 PSD 导入（用户在 PSD 里改图后直接导回）。模式由 Option 全局设置决定。"""
        if not hasattr(self.asset_manager, "meta") or self.asset_manager.meta is None:
            QMessageBox.warning(self, self.tr("AzurLane Tachie Helper"), self.tr("Open a metadata first"))
            return
        meta = self.asset_manager.meta.path
        last = os.path.dirname(Config.get_recent_path()) if Config.get_recent_path() else os.getcwd()
        psd, _ = QFileDialog.getOpenFileName(self, self.tr("Select PSD"), last, "PSD (*.psd)")
        if not psd:
            return
        face_mode = Config.get_face_mode()
        self.statusBar().showMessage(
            self.tr("Importing from PSD") + f" {os.path.basename(psd)} ({face_mode.name.lower()}) ..."
        )
        self._start_psd_worker(PsdImportWorker(psd, meta, face_mode))

    def refresh_statusbar(self):
        face_mode = self.face_mode_map[Config.get_face_mode()]
        self.msg_face_mode.setText(self.tr("Paintingface Mode") + self.tr(": ") + face_mode)

        server = self.server_map[Config.get_server()]
        self.msg_server.setText(self.tr("Server") + self.tr(": ") + server)

        skip = self.tr("On") if Config.get_skip_missing() else self.tr("Off")
        self.msg_skip_missing.setText(self.tr("Skip Missing") + self.tr(": ") + skip)

    def show_path(self, text: str):
        msg_box = QMessageBox()
        msg_box.setWindowTitle(self.tr("AzurLane Tachie Helper"))
        msg_box.setText(self.tr("Successfully written into") + self.tr(": ") + f"\n{text}")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def open_metadata(self, file: str):
        Config.set_recent_path(file)
        name = os.path.basename(file)
        self.msg_file.setText(f"({name}) {QDir.toNativeSeparators(file)}")
        logger.hr(name, 1)
        logger.attr("Metadata", file)

        self.tPainting.table.clearContents()
        self.tFace.table.clearContents()
        self.tIcon.table.clearContents()

        self.asset_manager.analyze(file)

        self.tPainting.set_data(self.asset_manager.layers)

        face_layer = self.asset_manager.face_layer
        if face_layer is not None:
            prefered = prefered_layer(self.asset_manager.layers, face_layer)
            self.tFace.set_data(self.asset_manager.faces, face_layer, prefered)
            self.tIcon.set_data(self.asset_manager.icons, face_layer)
        else:
            self.tFace.table.clearContents()
            self.tIcon.table.clearContents()

        self.preview.setAcceptDrops(True)
        self.mFile.aDecodePsd.setEnabled(True)
        self.mFile.aImportPsd.setEnabled(True)
        self.mFile.aExportImages.setEnabled(True)
        self.mFile.aImportImages.setEnabled(True)
        self.mFile.aExportImport.setEnabled(True)
        self.mEdit.aClipAllIcons.setEnabled(True)
        self.mEdit.aClipShipyardicon.setEnabled(True)
        self.mEdit.aClipHerohrzicon.setEnabled(True)
        self.mEdit.aClipSquareicon.setEnabled(True)

    def onOpenMetadata(self):
        last = Config.get_recent_path()
        file, _ = QFileDialog.getOpenFileName(self, self.tr("Select Metadata"), last)
        if file:
            self.open_metadata(file)

    def import_icon(self, files: list[str]):
        with ThreadPoolExecutor(max_workers=8) as executor:
            executor.map(self.tIcon.load, files)
        self.preview.refresh()

    def onImportIcons(self):
        last = os.path.dirname(Config.get_recent_path())
        files, _ = QFileDialog.getOpenFileNames(self, self.tr("Select Icons"), last, "Image (*.png)")
        if files:
            self.import_icon(files)

    def onEditClip(self):
        self._clip_icons(None)

    def onEditClipIcon(self, kind: str):
        self._clip_icons([kind])

    def _clip_icons(self, kinds: list[str] = None):
        """图标裁剪公共逻辑：kinds=None 裁剪全部三种图标；指定时只裁剪对应图标。裁剪后自动 encode。"""
        last = os.path.dirname(Config.get_recent_path())
        file, _ = QFileDialog.getOpenFileName(self, self.tr("Select Reference"), last, "Image (*.png)")
        if file:
            full, center = self.asset_manager.prepare_icon(file)
            viewer = IconViewer(self.asset_manager.meta.name_stem, self.asset_manager.icons, full, center, kinds)
            if viewer.exec():
                Config.set_presets(self.asset_manager.meta.name_stem, viewer.presets)
                res = self.asset_manager.clip_icons(file, viewer.presets, kinds)
                self.import_icon(res)
                self._encode()  # clip 后自动 encode（写回 bundle 到 output_{模式}）

    def onDecodeToPsd(self):
        base = os.path.dirname(self.asset_manager.meta.path)
        res = self.asset_manager.decode(base)
        self.show_path(QDir.toNativeSeparators(res))

    def _encode(self):
        """把已导入的替换贴图编码写回游戏资源（clip 后 / 预览区拖拽导入后自动触发）。"""
        base = os.path.dirname(self.asset_manager.meta.path)
        res = self.asset_manager.encode(base)
        self.show_path("\n".join(map(QDir.toNativeSeparators, res)))

    def onToggleFaceMode(self):
        if hasattr(self.tPainting, "layers"):
            with ThreadPoolExecutor(max_workers=8) as executor:
                executor.map(lambda x: x.refresh(), self.tPainting.layers.values())
            self.preview.sync_slider()  # 模式切换时同步扩展微调框显隐（custom 且选中 painting/face 才显示）
            self.preview.refresh()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            if not event.isAccepted():
                event.accept()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            files = filter(os.path.isfile, map(lambda x: x.toLocalFile(), event.mimeData().urls()))
            metadatas = list(filter(lambda x: "." not in os.path.basename(x), files))
            if metadatas != []:
                self.open_metadata(metadatas[0])
                event.accept()
            else:
                self.preview.dropEvent(event)
