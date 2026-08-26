from functools import partial
from typing import Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from ..base import Config
from ..base.Data import FaceModeType


class File(QMenu):
    def __init__(self, *cbs: list[Callable]):
        super().__init__()
        self.setTitle(self.tr("File"))

        # 区域 1 · 文件打开
        self.aOpenMetadata = QAction(self.tr("Open Metadata"), shortcut="Ctrl+S", enabled=True, triggered=cbs[0])
        # 区域 2 · PSD 相关
        self.aDecodePsd = QAction(self.tr("Decode to PSD"), shortcut="Ctrl+D", enabled=False, triggered=cbs[1])
        self.aImportPsd = QAction(self.tr("Import From PSD"), enabled=False, triggered=cbs[2])
        # 区域 3 · 普通流程（批量导入/导出，需先 Open Metadata 才能启用）
        self.aExportImages = QAction(self.tr("Export Images"), enabled=False, triggered=cbs[3])
        self.aImportImages = QAction(self.tr("Import From Images"), enabled=False, triggered=cbs[4])
        self.aExportImport = QAction(self.tr("Export && Import"), enabled=False, triggered=cbs[5])

        self.addAction(self.aOpenMetadata)
        self.addSeparator()
        self.addActions([self.aDecodePsd, self.aImportPsd])
        self.addSeparator()
        self.addActions([self.aExportImages, self.aImportImages, self.aExportImport])


class Edit(QMenu):
    def __init__(self, *cbs: list[Callable]):
        super().__init__()
        self.setTitle(self.tr("Icon"))

        # 图标裁剪：一键三种（原 Clip Icons 改名）+ 各自独立入口；裁剪后自动 encode，无手动 Encode
        self.aClipAllIcons = QAction(self.tr("Clip All Icons"), shortcut="Ctrl+C", enabled=False, triggered=cbs[0])
        self.aClipShipyardicon = QAction(self.tr("Clip Shipyard Icon"), enabled=False, triggered=cbs[1])
        self.aClipHerohrzicon = QAction(self.tr("Clip Herohrz Icon"), enabled=False, triggered=cbs[2])
        self.aClipSquareicon = QAction(self.tr("Clip Square Icon"), enabled=False, triggered=cbs[3])

        self.addActions(
            [self.aClipAllIcons, self.aClipShipyardicon, self.aClipHerohrzicon, self.aClipSquareicon]
        )


class FaceMode(QMenu):
    def __init__(self, *cbs: list[Callable]):
        super().__init__()
        self.setTitle(self.tr("Paintingface Mode"))

        self.cbs = cbs
        self.aOff = QAction(self.tr("Off"), checkable=True, triggered=partial(self.toggle, mode=FaceModeType.Off))
        self.aAuto = QAction(self.tr("Auto"), checkable=True, triggered=partial(self.toggle, mode=FaceModeType.Auto))
        self.aFull = QAction(self.tr("Full"), checkable=True, triggered=partial(self.toggle, mode=FaceModeType.Full))
        self.aCustom = QAction(
            self.tr("Custom"), checkable=True, triggered=partial(self.toggle, mode=FaceModeType.Custom)
        )

        self.addActions([self.aOff, self.aAuto, self.aFull, self.aCustom])
        self.flush()

    def toggle(self, _: bool, mode: FaceModeType):
        Config.set_face_mode(mode)
        self.cbs[1]()
        self.flush()

    def flush(self):
        mode = Config.get_face_mode()
        self.aOff.setChecked(mode == FaceModeType.Off)
        self.aAuto.setChecked(mode == FaceModeType.Auto)
        self.aCustom.setChecked(mode == FaceModeType.Custom)
        self.aFull.setChecked(mode == FaceModeType.Full)
        self.cbs[0]()


class MeshMode(QMenu):
    def __init__(self):
        super().__init__()
        self.setTitle(self.tr("Mesh Decoding Mode"))

        self.aZero = QAction(self.tr("Mode") + " 0", checkable=True, triggered=partial(self.toggle, mode=0))
        self.aOne = QAction(self.tr("Mode") + " 1", checkable=True, triggered=partial(self.toggle, mode=1))

        self.addActions([self.aZero, self.aOne])
        self.flush()

    def toggle(self, _: bool, mode: int):
        Config.set_mesh_mode(mode)
        self.flush()

    def flush(self):
        mode = Config.get_mesh_mode()
        self.aZero.setChecked(mode == 0)
        self.aOne.setChecked(mode == 1)


class Server(QMenu):
    def __init__(self, cb: Callable):
        super().__init__()
        self.setTitle(self.tr("Server"))

        self.cb = cb
        self.aCN = QAction(self.tr("CN"), checkable=True, triggered=partial(self.toggle, server="CN"))
        self.aJP = QAction(self.tr("JP"), checkable=True, triggered=partial(self.toggle, server="JP"))
        self.aEN = QAction(self.tr("EN"), checkable=True, triggered=partial(self.toggle, server="EN"))

        self.addActions([self.aCN, self.aJP, self.aEN])
        self.flush()

    def is_server(self, server: str):
        return Config.get_server() == server

    def toggle(self, _: bool, server: str):
        Config.set_server(server)
        self.flush()

    def flush(self):
        self.aCN.setChecked(self.is_server("CN"))
        self.aJP.setChecked(self.is_server("JP"))
        self.aEN.setChecked(self.is_server("EN"))
        self.cb()


class Option(QMenu):
    def __init__(self, *cbs: list[Callable]):
        super().__init__()
        self.setTitle(self.tr("Option"))

        self.cbs = cbs
        self.aFaceMode = FaceMode(*cbs)
        self.aMeshMode = MeshMode()
        self.mServer = Server(cbs[0])
        self.aSkipMissing = QAction(
            self.tr("Skip Missing Resources"), checkable=True, triggered=self.toggle_skip_missing
        )

        self.addMenu(self.aFaceMode)
        self.addMenu(self.aMeshMode)
        self.addSeparator()
        self.addMenu(self.mServer)
        self.addAction(self.aSkipMissing)
        self.flush()

    def toggle_skip_missing(self, _: bool):
        Config.set_skip_missing(self.aSkipMissing.isChecked())
        self.cbs[0]()

    def flush(self):
        self.aSkipMissing.setChecked(Config.get_skip_missing())
