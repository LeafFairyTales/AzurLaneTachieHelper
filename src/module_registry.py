"""模块注册中心：宿主从这里发现并加载所有功能模块。

开发约定：
- 新增功能模块 = 新建 `src/<模块文件>.py`（内含 Module 子类 + @register），
  并把模块文件名加入 MODULE_FILES（宿主逐个 try import，避免单个模块的
  问题拖垮宿主与其它模块 —— 开发层故障隔离）。
- 发布裁剪：构建时设环境变量 `ALTH_EXCLUDE_MODULES`（逗号分隔的模块 name，
  如 "Live2D"），被排除的模块不参与加载；默认全部加载。
"""
import os
import sys
from importlib import import_module

from PySide6.QtWidgets import QWidget


class Module(QWidget):
    """功能模块基类：宿主将其放入左侧导航 + 中央堆叠区。

    模块自持全部功能 UI（工具条/菜单按钮/内容/状态行），模块间互不引用。
    name 用于左侧导航显示与发布排除匹配（建议走 tr 翻译）。
    """

    name = "Module"

    def __init__(self, parent=None):
        super().__init__(parent)


MODULES: list[type[Module]] = []

# (来源模块名, 类)；来源 = register 调用处模块文件名的末段（与 MODULE_FILES 对齐）
_REGISTERED: list[tuple[str, type[Module]]] = []

# 需要 import 的模块文件（src 包内，触发各文件里的 @register）。
# 新增模块时在此追加一行（单文件模块名或包名均可）。
MODULE_FILES: list[str] = ["TachieHelper", "live2d"]


def register(klass: type[Module]) -> type[Module]:
    """类装饰器：把模块类登记进注册表（附来源模块名，load_all 按 MODULE_FILES 归属）。"""
    caller = sys._getframe(1).f_globals.get("__name__", "")
    source = caller.rsplit(".", 1)[-1]
    MODULES.append(klass)
    _REGISTERED.append((source, klass))
    return klass


def excluded_names() -> set[str]:
    """发布排除列表：环境变量 ALTH_EXCLUDE_MODULES="Live2D,Tachie"。"""
    raw = os.environ.get("ALTH_EXCLUDE_MODULES", "")
    return {x.strip() for x in raw.split(",") if x.strip()}


def load_all() -> list[type[Module]]:
    """按 MODULE_FILES 顺序逐个 try import 模块文件并返回排除后的注册类。

    - import 失败只打印日志并继续（该模块文件整体失效，不影响宿主与其它模块）；
    - 返回顺序与 MODULE_FILES 一致，且不依赖外部 import 时机。
    """
    exc = excluded_names()
    for mod_name in MODULE_FILES:
        try:
            import_module(f"{__package__}.{mod_name}")
        except Exception as e:  # noqa: BLE001 —— 模块故障隔离点
            print(f"[module_registry] failed to import module {mod_name}: {e!r}")
    by_source: dict[str, list[type[Module]]] = {}
    for source, klass in _REGISTERED:
        by_source.setdefault(source, []).append(klass)
    ordered: list[type[Module]] = []
    for mod_name in MODULE_FILES:
        ordered.extend(by_source.get(mod_name, []))
    return [k for k in ordered if k.name not in exc]