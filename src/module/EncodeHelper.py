import os
import struct
from typing import Literal
import UnityPy
from PIL import Image
from rich.progress import Progress
from UnityPy.classes import Sprite, Texture2D
from UnityPy.enums import ClassIDType, TextureFormat
from UnityPy.files import ObjectReader

from ..base import Config
from ..base.Data import FaceModeType
from ..base.Layer import FaceLayer, IconLayer, Layer
from ..base.Vector import Vector2
from ..utility import check_and_save


def output_dir_name() -> str:
    """当前 Paintingface 模式对应的输出目录名（output_off / output_auto / output_custom）。"""
    return f"output_{Config.get_face_mode().name.lower()}"


def set_sprite(sprite: Sprite, img: Image.Image):
    w, h = img.size
    old_w, old_h = sprite.m_Rect.width, sprite.m_Rect.height
    sprite.m_Rect.width, sprite.m_Rect.height = w, h
    sprite.m_RD.textureRect.width, sprite.m_RD.textureRect.height = w, h
    # uvTransform = (scale, centerX, scale, centerY)：rect 已按新图更新，
    # 中心必须同步，否则渲染仍按旧 rect 中心采样（sprite 显示不变）
    try:
        uv = sprite.m_RD.uvTransform
        uv.y, uv.w = w / 2, h / 2
    except (AttributeError, TypeError):
        pass
    # 渲染网格 m_VertexData：position = rect 世界坐标（±rect/2/PixelsToUnits），
    # 简单四边形按新/旧尺寸比例缩放；多边形 Sprite（差分表情脸型轮廓）重写为
    # 覆盖整个新 rect 的矩形，否则轮廓外区域不显示（底部不规则透明）。
    # UV 保持（原版即 0，游戏 UI 自建 mesh）
    if old_w and old_h:
        sx, sy = w / old_w, h / old_h
        try:
            vd = sprite.m_RD.m_VertexData
            n = vd.m_VertexCount
            if n != 4:
                ptu = sprite.m_PixelsToUnits or 100.0
                hw, hh = w / 2 / ptu, h / 2 / ptu
                pos = [-hw, hh, 0.0, hw, -hh, 0.0, hw, hh, 0.0, -hw, -hh, 0.0]
                uv = [0.0] * 8
                vd.m_VertexCount = 4
                vd.m_DataSize = struct.pack("<" + "f" * 20, *(pos + uv))
                sm = sprite.m_RD.m_SubMeshes[0]
                sm.indexCount = 6
                sm.vertexCount = 4
                sprite.m_RD.m_IndexBuffer = struct.pack("<" + "H" * 6, 3, 0, 1, 2, 1, 0)
            else:
                data = vd.m_DataSize
                floats = list(struct.unpack("<" + "f" * (len(data) // 4), data))
                pos_n = n * 3
                if len(floats) >= pos_n:
                    for i in range(pos_n):
                        if i % 3 == 0:
                            floats[i] *= sx
                        elif i % 3 == 1:
                            floats[i] *= sy
                    vd.m_DataSize = struct.pack("<" + "f" * len(floats), *floats)
        except (AttributeError, TypeError, struct.error):
            pass
        # 碰撞形状 m_PhysicsShape（世界坐标）同步缩放
        try:
            shape = sprite.m_PhysicsShape
            for poly in shape:
                for p in poly:
                    p.x *= sx
                    p.y *= sy
        except (AttributeError, TypeError):
            pass
    sprite.save()


def set_tex2d(tex2d: Texture2D, img: Image.Image):
    fmt = {"RGB": TextureFormat.RGB24, "RGBA": TextureFormat.RGBA32}[img.mode]
    tex2d.set_image(img.transpose(Image.Transpose.FLIP_TOP_BOTTOM), fmt)
    tex2d.save()


def set_mesh(mesh: ObjectReader, img: Image.Image):
    data = mesh.parse_as_dict()

    data["m_SubMeshes"][0]["indexCount"] = 6
    data["m_SubMeshes"][0]["vertexCount"] = 4
    data["m_IndexBuffer"] = [0, 0, 1, 0, 2, 0, 2, 0, 3, 0, 0, 0]

    w, h = img.size
    buf = [0, 0, 0, 0, 0, 0, h, 0, 0, 1, w, h, 0, 1, 1, w, 0, 0, 1, 0]
    data["m_VertexData"]["m_DataSize"] = struct.pack(mesh.reader.endian + "f" * 20, *buf)
    data["m_VertexData"]["m_VertexCount"] = 4

    mesh.patch(data)


def set_meta(reader: ObjectReader, size_delta: Vector2, pivot: Vector2, anchored_position: Vector2):
    data = reader.parse_as_dict()

    data["m_SizeDelta"] = size_delta.dict()
    data["m_Pivot"] = pivot.dict()
    data["m_AnchoredPosition"] = anchored_position.dict()

    reader.patch(data)


class EncodeHelper:
    @staticmethod
    def replace_painting(dir: str, layer: Layer, reader: ObjectReader) -> tuple[str, bool]:
        path = layer.path if layer.path != "Not Found" else layer.meta.path
        env = UnityPy.load(path)

        # 替换贴图 + mesh：背景（主立绘）repl 已按 rawSpriteSize 缩回，无 mesh 则不触发；
        # rw 保持原逻辑（repl = rawSpriteSize 显示尺寸，set_mesh 重写网格）
        for x in env.objects:
            match x.type:
                case ClassIDType.Texture2D:
                    set_tex2d(x.parse_as_object(), layer.repl)
                case ClassIDType.Mesh:
                    set_mesh(x, layer.repl)

        path = os.path.join(dir, output_dir_name(), "painting", os.path.basename(path))
        check_and_save(path, env.file.save(Config.get_compression()))

        if Config.get_face_mode() != FaceModeType.Custom:
            return path, False

        x1, y1, _, _ = Config.get_face_extension(layer.meta.name_stem, layer.validName)
        x_min, y_min, _, _ = layer.box
        pivot = layer.pivot - Vector2(max(x1, -x_min), max(y1, -y_min)) / layer.sizeDelta
        set_meta(reader, layer.sizeDelta, pivot, layer.anchoredPosition)

        return path, True

    @staticmethod
    def replace_face(
        dir: str, faces: dict[str, FaceLayer], reader: ObjectReader, progress: Progress
    ) -> tuple[str, bool]:
        first = list(faces.values())[0]
        layer = first.layer
        face_mode = Config.get_face_mode()

        # paintingface 文件与索引文件同名（用户可能改名，文件名 ≠ 内部名 name_stem）
        name = os.path.basename(layer.meta.path).removesuffix("_n")
        meta_dir = os.path.dirname(layer.meta.path)
        root = os.path.dirname(meta_dir)
        path = next(
            (p
             for p in [
                 os.path.join(meta_dir, "paintingface", name),
                 os.path.join(root, "paintingface", name),
             ]
             if os.path.exists(p)),
            None,
        )
        assert path, f"paintingface not found for {name}"
        env = UnityPy.load(path)

        cur, cnt = 0, len(faces)
        task = progress.add_task(f"Encode paintingface ({cur}/{cnt}):", total=cnt)
        for x in env.objects:
            if x.type == ClassIDType.Sprite:
                sprite: Sprite = x.parse_as_object()
                if sprite.m_Name in faces:
                    if face_mode != FaceModeType.Off:
                        set_sprite(sprite, faces[sprite.m_Name].repl)
                    set_tex2d(sprite.m_RD.texture.deref_parse_as_object(), faces[sprite.m_Name].repl)
                    cur += 1
                    progress.update(task, advance=1, description=f"Encode paintingface ({cur}/{cnt}):")

        path = os.path.join(dir, output_dir_name(), "paintingface", name)
        check_and_save(path, env.file.save(Config.get_compression()))

        if face_mode == FaceModeType.Off:
            return path, False

        if face_mode == FaceModeType.Auto or face_mode == FaceModeType.Full:
            # Auto=最小图层（立绘主体），Full=最大图层（背景/整幅画布）：均按参考图层重算布局
            prefered = first.prefered
            size_delta = prefered.sizeDelta
            pivot = prefered.pivot
            anchored_position = prefered.pivotPosition - layer.pivotPosition + layer.anchoredPosition
        elif face_mode == FaceModeType.Custom:
            size_delta = Vector2(first.repl.size)
            # extension 以内部名 name_stem 为 key（导入准备时 set_face_extension 用 name_stem 存）
            x1, y1, _, _ = Config.get_face_extension(layer.meta.name_stem, "paintingface")
            x_min, y_min, _, _ = layer.box
            pivot = (layer.sizeDelta * layer.pivot - Vector2(max(x1, -x_min), max(y1, -y_min))) / size_delta
            anchored_position = layer.anchoredPosition

        set_meta(reader, size_delta, pivot, anchored_position)

        return path, True

    @staticmethod
    def replace_icon(dir: str, kind: Literal["shipyardicon", "herohrzicon", "squareicon"], icon: IconLayer) -> str:
        env = UnityPy.load(icon.path)
        for v in env.container.values():
            if v.type == ClassIDType.Sprite:
                set_sprite(v.deref_parse_as_object(), icon.repl)
            elif v.type == ClassIDType.Texture2D:
                set_tex2d(v.deref_parse_as_object(), icon.repl)

        path = os.path.join(dir, output_dir_name(), kind, icon.layer.meta.name_stem)
        check_and_save(path, env.file.save(Config.get_compression()))

        return path

    @staticmethod
    def exec(dir: str, layers: dict[str, Layer], faces: dict[str, FaceLayer], icons: dict[str, IconLayer]) -> list[str]:
        meta_path = list(layers.values())[0].meta.path
        meta_env = UnityPy.load(meta_path)
        readers = list(meta_env.cabs.values())[0].objects
        result = []
        with Progress() as progress:
            valid = [v for v in layers.values() if v.modified]
            painting_modified = valid != []
            if valid != []:
                cur, cnt = 0, len(valid)
                task = progress.add_task(f"Encode painting ({cur}/{cnt}):", total=cnt)
                for x in valid:
                    sub, _ = EncodeHelper.replace_painting(dir, x, readers[x.pathId])
                    result += [sub]
                    cur += 1
                    progress.update(task, advance=1, description=f"Encode painting ({cur}/{cnt}):")

            valid = {k: v for k, v in faces.items() if v.modified}
            face_modified = valid != {}
            if valid != {}:
                face_layer = list(valid.values())[0].layer
                sub, _ = EncodeHelper.replace_face(dir, valid, readers[face_layer.pathId], progress)
                result += [sub]

            valid = {k: v for k, v in icons.items() if v.modified and os.path.exists(v.path)}
            if valid != {}:
                cur, cnt = 0, len(valid)
                task = progress.add_task(f"Encode icon ({cur}/{cnt}):", total=cnt)
                for k, v in valid.items():
                    result += [EncodeHelper.replace_icon(dir, k, v)]
                    cur += 1
                    progress.update(task, advance=1, description=f"Encode icon ({cur}/{cnt}):")

        # 索引 bundle：仅当立绘/表情图层有修改时才输出索引（icons 裁剪不改变索引，
        # 输出反而会用源索引覆盖同模式下已导入立绘的修改版索引）；
        # off 模式 painting/face 修改时索引为原样复制，保证替换回游戏时全套覆盖
        if painting_modified or face_modified:
            path = os.path.join(dir, output_dir_name(), "painting", os.path.basename(meta_path))
            check_and_save(path, meta_env.file.save(Config.get_compression()))
            result += [path]

        return result
