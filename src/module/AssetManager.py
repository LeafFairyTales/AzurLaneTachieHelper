import os
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import UnityPy
from PIL import Image, ImageOps
from UnityPy.classes import GameObject, MonoBehaviour, Texture2D
from UnityPy.enums import ClassIDType

from ..base import Config
from ..base.Data import IconPreset, IconPresets, MetaInfo
from ..base.Layer import FaceLayer, IconLayer, Layer, prefered_layer
from ..base.Vector import Vector2
from ..logger import logger
from ..ui.IconViewer import get_padding
from ..utility import open_and_transpose
from .AdbHelper import AdbHelper
from .DecodeHelper import DecodeHelper
from .EncodeHelper import EncodeHelper


class AssetManager:
    def __init__(self):
        self.init()

    def init(self):
        self.meta: MetaInfo = None
        self.deps: dict[str, str] = {}
        self.layers: dict[str, Layer] = {}
        self.faces: dict[str, FaceLayer] = {}
        self.icons: dict[str, IconLayer] = {}

    @property
    def face_layer(self):
        return self.layers["face"]

    def decode(self, dir: str) -> str:
        faces = {int(k): v for k, v in self.faces.items()}
        psd = DecodeHelper.exec(self.layers, faces)
        path = os.path.join(dir, f"{self.meta.name}.psd")
        if os.path.exists(path):
            old = [x for x in os.listdir(dir) if re.match(rf"{self.meta.name}\.bak_\d+\.psd", x)]
            num = sorted([eval(re.search(r"bak_(\d+).psd", x).group(1)) for x in old])
            last = 1 if old == [] else num[-1] + 1
            os.rename(path, os.path.join(dir, f"{self.meta.name}.bak_{last}.psd"))
        with open(path, "wb") as f:
            psd.write(f)
        return path

    def encode(self, dir: str) -> str:
        return EncodeHelper.exec(dir, self.layers, self.faces, self.icons)

    def get_dependency(self, file: str) -> list[str]:
        try:
            if not os.path.exists("dependencies"):
                AdbHelper.pull("dependencies", add_prefix=True)
            env = UnityPy.load("dependencies")
            mb: MonoBehaviour = [x.parse_as_object() for x in env.objects if x.type == ClassIDType.MonoBehaviour][0]
            idx = mb.m_Keys.index(f"painting/{os.path.basename(file)}")
            return mb.m_Values[idx].m_Dependencies
        except Exception:
            if not Config.get_skip_missing():
                raise
        # Skip Missing 开启时的离线回退：扫描索引同目录下同基名的贴图 bundle
        base = os.path.basename(file).removesuffix("_n")
        dirname = os.path.dirname(file)
        deps = [
            f
            for f in os.listdir(dirname)
            if os.path.isfile(os.path.join(dirname, f))
            and f.startswith(base)
            and f.endswith("_tex")
            and f != os.path.basename(file)
        ]
        return deps

    def analyze(self, file: str):
        self.init()

        self.deps = self.get_dependency(file)
        logger.attr("Dependencies", ", ".join(self.deps))

        env = UnityPy.load(file)
        for dep in self.deps:
            path = os.path.join(os.path.dirname(file) + "/", dep)
            if not os.path.exists(path):
                if Config.get_skip_missing():
                    logger.attr("Skipped missing dependency", dep)
                    continue
                raise FileNotFoundError(f"Dependency not found: {dep}")
            env.load_file(path)

        file_map = {
            os.path.basename(x)[:-4].lower(): k
            for k, v in env.files.items()
            for x in v.container.keys()
            if not k.endswith("commonui_atlas") and x.endswith(".png")
        }

        base_go: GameObject = [
            x.deref_parse_as_object() for x in env.container.values() if x.type == ClassIDType.GameObject
        ][0]
        base_layer = Layer(base_go.m_Component[0].component)

        self.layers = base_layer.flatten()
        if "face" not in [x.name for x in self.layers.values()]:
            self.layers["face"] = base_layer.get_child("face")

        for k in set(self.layers.keys()) - {"face"}:
            layer = self.layers[k]
            if layer.texture2D is None or (Config.get_skip_missing() and layer.mesh_missing):
                if Config.get_skip_missing():
                    logger.attr("Skipped missing layer", layer.name)
                self.layers.pop(k)
            else:
                logger.attr(layer.__repr__(), layer.__str__())

        usable = [x for x in self.layers.values() if x is not None]
        if not usable:
            raise RuntimeError("No usable layers: all sprites/textures are missing")
        x_min = min([_.posMin.X for _ in usable])
        x_max = max([_.posMax.X for _ in usable])
        y_min = min([_.posMin.Y for _ in usable])
        y_max = max([_.posMax.Y for _ in usable])
        size = Vector2(x_max - x_min, y_max - y_min)
        bias = Vector2(-x_min, -y_min)

        self.meta = MetaInfo(file, base_layer.name, size, bias)

        base = os.path.basename(file).removesuffix("_n")
        painting_dir = os.path.dirname(file)
        root = os.path.dirname(painting_dir)
        path = next(
            (
                p
                for p in [
                    os.path.join(painting_dir, "paintingface", base),
                    os.path.join(root, "paintingface", base),
                ]
                if os.path.exists(p)
            ),
            None,
        )
        if path:
            try:
                env = UnityPy.load(path)
                tex2ds: list[Texture2D] = [
                    x.parse_as_object() for x in env.objects if x.type == ClassIDType.Texture2D
                ]
                self.faces = {x.m_Name: FaceLayer(self.meta, x, path) for x in tex2ds}
                self.faces = {k: v for k, v in sorted(self.faces.items(), key=lambda x: int(x[0]))}
            except Exception:
                if not Config.get_skip_missing():
                    raise
                logger.attr("Skipped paintingface", base)

        for k in set(self.layers.keys()):
            v = self.layers[k]
            v.meta = self.meta
            if k == "face":
                continue
            name = v.texture2D.m_Name.lower()
            if name not in file_map:
                if Config.get_skip_missing():
                    logger.attr("Skipped missing texture", v.texture2D.m_Name)
                    self.layers.pop(k)
                    continue
                raise KeyError(f"Texture not found in loaded bundles: {name}")
            v.path = file_map[name]
            if Config.get_face_extension(self.meta.name_stem, k) is None:
                Config.set_face_extension(self.meta.name_stem, k, [0] * 4)

        presets = IconPresets()
        for k, v in presets.to_dict().items():
            path = next(
                (
                    p
                    for p in [
                        os.path.join(painting_dir, k, base),
                        os.path.join(painting_dir, k, base + ".ys"),
                        os.path.join(root, k, base),
                        os.path.join(root, k, base + ".ys"),
                    ]
                    if os.path.exists(p)
                ),
                None,
            )
            if path:
                try:
                    env = UnityPy.load(path)
                    icon_layer = None
                    for x in env.objects:
                        if x.type == ClassIDType.Texture2D:
                            tex2d: Texture2D = x.parse_as_object()
                            # 名字匹配优先；内部名 ≠ 文件名（用户改名）时兜底取第一个 Texture2D
                            if icon_layer is None or re.match(f"(?i)^{base}$", tex2d.m_Name):
                                icon_layer = IconLayer(self.meta, tex2d, path)
                    self.icons[k] = icon_layer
                except Exception:
                    if not Config.get_skip_missing():
                        raise
                    logger.attr("Skipped icon", f"{k}/{base}")

    def clip_icons(self, workload: str, presets: IconPresets, kinds: list[str] = None) -> list[str]:
        full, center = self.prepare_icon(workload)

        # kinds=None 裁剪全部三种图标；指定时只裁剪对应图标
        items = {k: presets[k] for k in (kinds or list(presets.to_dict().keys())) if k in presets.to_dict()}

        def clip(kind: str, preset: IconPreset):
            w, h = preset.size / preset.scale
            x, y = center - Vector2(w, h) * preset.pivot

            pad_x, pad_y = get_padding(*full.size, (x + w / 2, y + h / 2), preset.angle)
            img = ImageOps.expand(full, border=(0, 0, pad_x, pad_y)).rotate(
                preset.angle, Image.Resampling.BICUBIC, center=(x + w / 2, y + h / 2)
            )
            if kind == "shipyardicon":
                sub = img.copy().crop((0, 0, x + w, y + h))
                img = Image.new("RGBA", sub.size)
                img.paste(sub, (round(-10 / preset.scale), 0))
                data = np.array(img)
                data[..., :3] = 0
                data[..., 3] = np.where(data[..., 3] > 76, 76, data[..., 3])
                img = Image.fromarray(data)
                img.alpha_composite(sub)

            # 图标裁剪产物输出到导出文件夹 image_{模式}（与图层 PNG 同处）；bundle 加密输出留在 output_{模式}
            mode_name = Config.get_face_mode().name.lower()
            out_dir = os.path.join(os.path.dirname(self.meta.path), f"image_{mode_name}")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"{kind}.png")
            img.crop((x, y, x + w, y + h)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(path)

            return path

        with ThreadPoolExecutor(max_workers=8) as executor:
            output = executor.map(clip, items.keys(), items.values())

        return list(output)

    def prepare_icon(self, file: str) -> tuple[Image.Image, Vector2]:
        """整图直接导入，不裁剪不缩放，纯让用户在完整图上调整图标框。

        face 中心（画布坐标）按参考图与画布尺寸比例映射到参考图像素坐标，
        保证裁剪框初始位置落在脸部附近；任何尺寸/内容的参考图都可操作。
        """
        full = open_and_transpose(file)
        cw, ch = self.meta.size.round().tuple()
        fw, fh = full.size
        fc = self.face_layer.posMin + self.face_layer.sizeDelta / 2  # face 中心（画布坐标）
        center = Vector2(fc.X * fw / cw, fc.Y * fh / ch)
        return full, center
