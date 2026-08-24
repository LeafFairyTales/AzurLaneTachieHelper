r"""批量导入（加密）助手。

把「解码图层 → 导出 PNG（含表情合成）→ 三模式导入 → from-export 闭环」整合为
项目内模块，供 GUI 调用，最终随 exe 封装。

用法（GUI 或编程）:
    from src.module.ImportHelper import ImportHelper
    ImportHelper.run_many(["baofengyu", "feiyun"], root=r"...\import_work",
                          face_mode=FaceModeType.Auto, from_export=True)
"""
import os
import shutil

from PIL import Image

from ..base import Config
from ..base.Data import FaceModeType
from ..base.Layer import prefered_layer
from ..logger import logger
from ..utility import open_and_transpose
from .AssetManager import AssetManager


class ImportHelper:
    @staticmethod
    def _clean_output(base: str, face_mode: FaceModeType):
        """规则：每次导入前清理该船当前模式旧输出（output_{off/auto/custom}），只留一份最新。"""
        out_dir = os.path.join(base, f"output_{face_mode.name.lower()}")
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
            logger.info(f"cleaned old output: {out_dir}")

    @staticmethod
    def _compose_standee(am: AssetManager) -> Image.Image:
        """立绘合成：主图 + 各 rw 图层按 box 叠加（排除 paintingface），返回整幅立绘（倒像）。"""
        base_full = None
        for k, v in am.layers.items():
            if k == "face":
                continue
            img = v.decode()
            if base_full is None:
                base_full = img.copy()
            else:
                base_full = base_full.copy()
                base_full.alpha_composite(img, (v.box[0], v.box[1]))
        return base_full

    @staticmethod
    def _prepare_paintings(am: AssetManager, export_dir: str, from_export: bool):
        """painting 图层：导出正像 PNG + 设 repl（内部合成 = decode 图；from-export = export 图翻转）。

        注意：repl 按 rawSpriteSize 缩回 —— 背景（主立绘）rawSpriteSize ≠ sizeDelta 时不缩回则
        游戏渲染放大；rw 的 rawSpriteSize == sizeDelta（mesh 变形显示尺寸），天然不缩回
        （不能缩到贴图像素尺寸，比例不同会拉伸变形）。
        """
        for k, v in am.layers.items():
            if k == "face":
                continue
            target = v.rawSpriteSize.round() if v.rawSpriteSize is not None else v.texture2D.image.size
            p = os.path.join(export_dir, f"{k}.png")
            if from_export:
                if not os.path.exists(p):
                    logger.warning(f"painting {k}: export PNG 缺失 {p}，跳过")
                    continue
                v.modified = True
                img = open_and_transpose(p)
                if img.size != target:
                    img = img.resize(target, Image.Resampling.BICUBIC)
                v.repl = img
                logger.info(f"painting {k}: from-export repl={v.repl.size}")
            else:
                img = v.decode()
                img.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(p)  # export 正像（sizeDelta 显示尺寸）
                v.modified = True
                if img.size != target:
                    img = img.resize(target, Image.Resampling.BICUBIC)
                v.repl = img
                logger.info(f"painting {k}: {img.size} -> {os.path.basename(p)}")

    @staticmethod
    def _prepare_faces(am: AssetManager, export_dir: str, face_mode: FaceModeType, from_export: bool):
        """faces：按模式分流。
        off   -> repl = decode() 单脸（paintingface 原图）
        auto/full/custom -> repl = crop_face()：表情模板 = 立绘合成 + 对应表情图叠加，按 prefered/扩展框裁出
        from_export 时直接用 export PNG（正像）翻转还原为 repl。
        """
        if am.face_layer is not None:
            prefered = prefered_layer(am.layers, am.face_layer, largest=(face_mode == FaceModeType.Full))
            for v in am.faces.values():
                v.set_data(am.face_layer, prefered)
            if (
                face_mode == FaceModeType.Custom
                and Config.get_face_extension(am.face_layer.meta.name_stem, "paintingface") is None
            ):
                fe = [a - b for a, b in zip(prefered.box, am.face_layer.box)]
                Config.set_face_extension(am.face_layer.meta.name_stem, "paintingface", fe)
                logger.info(f"set paintingface extension: {fe}")

        if face_mode != FaceModeType.Off:
            base_full = ImportHelper._compose_standee(am)
            if base_full is None:
                logger.warning("无立绘图层，face 将无法按整幅图导入")
            fx, fy = am.face_layer.box[0], am.face_layer.box[1] if am.face_layer is not None else (0, 0)
        else:
            base_full = None
            fx = fy = 0

        for k, v in am.faces.items():
            v.modified = True
            if face_mode == FaceModeType.Off:
                if from_export:
                    p = os.path.join(export_dir, f"face_{k}.png")
                    if not os.path.exists(p):
                        logger.warning(f"face {k}: export PNG 缺失")
                        v.modified = False
                        continue
                    v.repl = open_and_transpose(p)  # export 正像 -> 翻转 = repl
                else:
                    v.full = None
                    v.repl = v.decode()
            else:
                if from_export:
                    p = os.path.join(export_dir, f"face_{k}.png")
                    if not os.path.exists(p):
                        logger.warning(f"face {k}: export PNG 缺失")
                        v.modified = False
                        continue
                    v.repl = open_and_transpose(p)  # export 正像 -> 翻转 = repl
                else:
                    full = base_full.copy()
                    full.alpha_composite(v.decode(), (fx, fy))  # 叠加该 face 表情到脸部位置
                    v.full = full
                    v.refresh()  # repl = crop_face()
            img = v.repl
            if not from_export:
                img.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(
                    os.path.join(export_dir, f"face_{k}.png")
                )  # export 正像
            logger.info(f"face {k}: repl={img.size}")

    @staticmethod
    def export_layers(
        meta_path: str,
        face_mode: FaceModeType = FaceModeType.Off,
        out_base: str = None,
    ) -> str:
        """只导出图层 PNG（painting + face）到 painting/image_{模式}\，不导入。

        与导入共用导出逻辑：painting 导出 sizeDelta 显示尺寸正像（对应 PSD 画布）；
        face 按模式导出（off=单脸，auto/custom=立绘合成+表情）。
        编辑这些 PNG 后可用 from-export 模式导入（闭环）。
        """
        Config.set_skip_missing(True)
        Config.set_face_mode(face_mode)
        if not os.path.isfile(meta_path):
            logger.warning(f"metadata not found: {meta_path}")
            return None
        meta_dir = os.path.dirname(meta_path)
        ship = os.path.basename(meta_path).removesuffix("_n")
        out_base = out_base or meta_dir
        export_dir = os.path.join(out_base, f"image_{face_mode.name.lower()}")
        os.makedirs(export_dir, exist_ok=True)
        am = AssetManager()
        am.analyze(meta_path)
        ImportHelper._prepare_paintings(am, export_dir, from_export=False)
        ImportHelper._prepare_faces(am, export_dir, face_mode, from_export=False)
        logger.info(f"exported layers -> {export_dir}")
        return export_dir

    @staticmethod
    def export_many(
        meta_paths: list[str],
        face_mode: FaceModeType = FaceModeType.Off,
    ) -> dict[str, str]:
        """批量导出图层 PNG（逐船独立 AssetManager）。"""
        results = {}
        for meta in meta_paths:
            name = os.path.basename(meta)
            logger.hr(f"Export {name} ({face_mode.name})", 1)
            try:
                results[name] = ImportHelper.export_layers(meta, face_mode)
            except Exception as e:
                logger.error(f"{name} FAIL: {type(e).__name__}: {e}")
                results[name] = None
        return results

    @staticmethod
    def import_psd(
        psd_path: str,
        meta_path: str,
        face_mode: FaceModeType = FaceModeType.Off,
        out_base: str = None,
    ) -> list[str]:
        """从解码导出的 PSD 导入（用户在 PSD 里改图后直接导回，无需导出 PNG）。

        输入 = PSD 文件 + 索引 bundle（GUI 当前打开的元数据）。
        PSD 图层映射：`{name} [{贴图名}]` -> painting 图层；paintingface 组 `face #{N}` -> face N。
        流程：提取 PSD 图层（正像）-> 翻转成倒像 repl（painting 按 rawSpriteSize 缩回；
        face 按模式：off=单脸，auto/custom=PSD 画布合成+单脸叠加后 crop_face）-> encode。
        同时把图层合成图导出到 painting/image_{模式}/，供查看/后续 from-export 复用。
        """
        import numpy as np
        from pytoshop import PsdFile
        from pytoshop.user import nested_layers

        Config.set_skip_missing(True)
        Config.set_face_mode(face_mode)
        if not os.path.isfile(psd_path) or not os.path.isfile(meta_path):
            logger.warning(f"psd/meta not found: {psd_path} / {meta_path}")
            return []

        def layer_to_image(layer):
            h = layer.bottom - layer.top
            w = layer.right - layer.left
            get = lambda k, d: np.asarray(layer.channels[k].image) if k in layer.channels else d
            arr = np.stack(
                [
                    get(0, np.zeros((h, w), np.uint8)),
                    get(1, np.zeros((h, w), np.uint8)),
                    get(2, np.zeros((h, w), np.uint8)),
                    get(-1, np.full((h, w), 255, np.uint8)),
                ],
                axis=-1,
            ).astype(np.uint8)
            return Image.fromarray(arr, "RGBA")

        # 1) 解析 PSD 图层（懒加载，文件保持打开直到提取完）
        #    PS 另存副本的两处差异在此兼容：
        #    a) 图层名尾部追加 \x00（Pascal 字符串 padding）→ 清洗
        #    b) 图层 bounds 被裁剪到非透明内容范围（透明优化）→ 记录图层自身画布坐标，
        #       后续合成/裁剪用该坐标还原，而非 bundle 的 box
        f = open(psd_path, "rb")
        try:
            psd = PsdFile.read(f)
            nested = nested_layers.psd_to_nested_layers(psd)
            canvas_w, canvas_h = psd.width, psd.height
            paintings, paintings_pos, faces_psd = {}, {}, {}
            stack = [nested]
            while stack:
                ls = stack.pop()
                for l in ls:
                    if isinstance(l, nested_layers.Group):
                        stack.append(l.layers)
                        continue
                    if not (l.right > l.left and l.bottom > l.top):
                        continue  # 跳过空/零尺寸图层（PS 附加的空图层）
                    # PSD 图层为正像（y 向下），翻转还原为 repl/合成用的倒像（Unity y 向上）
                    img = layer_to_image(l).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    name = (l.name or "").strip().replace("\x00", "")
                    # 图层自身画布坐标（Unity 方向）：x = left，y = canvas_h - bottom
                    ux, uy = l.left, canvas_h - l.bottom
                    if name.endswith("]") and "[" in name:
                        key = name[name.rfind("[") + 1 : -1]
                        paintings[key] = img
                        paintings_pos[key] = (ux, uy)
                    elif name.startswith("face #"):
                        faces_psd[name[len("face #") :]] = (img, ux, uy)
        finally:
            f.close()

        if not paintings:
            logger.warning(f"PSD 无 painting 图层: {psd_path}")
            return []

        meta_dir = os.path.dirname(meta_path)
        out_base = out_base or meta_dir
        ship = os.path.basename(meta_path).removesuffix("_n")
        export_dir = os.path.join(out_base, f"image_{face_mode.name.lower()}")
        os.makedirs(export_dir, exist_ok=True)
        am = AssetManager()
        am.analyze(meta_path)

        # 2) painting：所有 PSD 图层按自身画布坐标贴回画布 → 从画布按 bundle 原 box 裁剪还原
        #    （PS 裁剪掉的透明边缘由此补回），repl 按 rawSpriteSize 缩回；同时导出正像 PNG
        canvas_size = am.meta.size.round().tuple()
        full = Image.new("RGBA", canvas_size)
        for k, v in am.layers.items():
            if k == "face":
                continue
            tex = v.texture2D.m_Name
            if tex in paintings:
                full.alpha_composite(paintings[tex], paintings_pos[tex])

        for k, v in am.layers.items():
            if k == "face":
                continue
            tex = v.texture2D.m_Name
            if tex not in paintings:
                logger.warning(f"painting {tex}: PSD 无对应图层，跳过")
                continue
            x1, y1, x2, y2 = v.box
            box = (max(0, x1), max(0, y1), min(x2, canvas_size[0]), min(y2, canvas_size[1]))
            img = full.crop(box)
            img.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(os.path.join(export_dir, f"{k}.png"))
            target = v.rawSpriteSize.round() if v.rawSpriteSize is not None else v.texture2D.image.size
            if img.size != target:
                img = img.resize(target, Image.Resampling.BICUBIC)
            v.modified = True
            v.repl = img
            logger.info(f"painting {tex}: PSD -> repl={img.size} (box={box})")

        # 3) faces：按模式（off=单脸 repl；auto/full/custom=PSD 画布合成 + 单脸叠加 -> crop_face）
        if am.face_layer is not None:
            prefered = prefered_layer(am.layers, am.face_layer, largest=(face_mode == FaceModeType.Full))
            for v in am.faces.values():
                v.set_data(am.face_layer, prefered)
            if (
                face_mode == FaceModeType.Custom
                and Config.get_face_extension(am.face_layer.meta.name_stem, "paintingface") is None
            ):
                fe = [a - b for a, b in zip(prefered.box, am.face_layer.box)]
                Config.set_face_extension(am.face_layer.meta.name_stem, "paintingface", fe)
                logger.info(f"set paintingface extension: {fe}")

        if face_mode != FaceModeType.Off:
            for k, v in am.faces.items():
                if k not in faces_psd:
                    logger.warning(f"face {k}: PSD 无对应图层，跳过")
                    continue
                img_f, ux, uy = faces_psd[k]
                f2 = full.copy()
                f2.alpha_composite(img_f, (ux, uy))  # face 放回自身画布坐标（PS 裁剪后仍正确）
                v.modified = True
                v.full = f2
                v.refresh()  # repl = crop_face()
                if v.repl is not None:
                    v.repl.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(os.path.join(export_dir, f"face_{k}.png"))
                logger.info(f"face {k}: PSD 合成 -> repl={v.repl.size if v.repl else None} @({ux},{uy})")
        else:
            fl = am.face_layer
            for k, v in am.faces.items():
                if k not in faces_psd:
                    logger.warning(f"face {k}: PSD 无对应图层，跳过")
                    continue
                img_f, ux, uy = faces_psd[k]
                # 单脸：图层贴回画布后按 paintingface 原 box 裁剪（还原 PS 裁剪掉的透明边缘）
                canvas_face = Image.new("RGBA", canvas_size)
                canvas_face.alpha_composite(img_f, (ux, uy))
                x1, y1, x2, y2 = fl.box
                box = (max(0, x1), max(0, y1), min(x2, canvas_size[0]), min(y2, canvas_size[1]))
                repl = canvas_face.crop(box)
                v.modified = True
                v.full = None
                v.repl = repl
                v.repl.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(os.path.join(export_dir, f"face_{k}.png"))
                logger.info(f"face {k}: PSD 单脸 -> repl={v.repl.size} @({ux},{uy})")

        # 4) encode
        res = am.encode(out_base)
        for r in res:
            logger.info(f"OUT: {r}")
        return res

    @staticmethod
    def run_meta(
        meta_path: str,
        export_dir: str = None,
        face_mode: FaceModeType = FaceModeType.Off,
        from_export: bool = False,
        out_base: str = None,
    ) -> list[str]:
        """对任意索引 bundle（元数据路径）执行导入（加密）流程，返回输出文件列表。

        meta_path   : 索引 bundle（无扩展名元数据文件）的完整路径，任意位置
        export_dir  : 图层 PNG 导出目录；None 时默认 `painting/image_{模式}`
        face_mode   : Off / Auto / Custom
        from_export : True 时用 export PNG 作为导入源（用户改图后导入）
        out_base    : 加密输出根（{out_base}/output/...）；None 时自动判定船目录
        """
        Config.set_skip_missing(True)
        Config.set_face_mode(face_mode)

        if not os.path.isfile(meta_path):
            logger.warning(f"metadata not found: {meta_path}")
            return []

        meta_dir = os.path.dirname(meta_path)
        ship = os.path.basename(meta_path)
        # 数据结构约定（固定）：索引 bundle 位于 {数据根}/painting/{meta}，
        # paintingface / shipyardicon / herohrzicon / squareicon 必定同在 {数据根}/ 下
        out_base = out_base or meta_dir
        if export_dir is None:
            export_dir = os.path.join(out_base, f"image_{face_mode.name.lower()}")
        os.makedirs(export_dir, exist_ok=True)

        ImportHelper._clean_output(out_base, face_mode)
        am = AssetManager()
        am.analyze(meta_path)

        ImportHelper._prepare_paintings(am, export_dir, from_export)
        ImportHelper._prepare_faces(am, export_dir, face_mode, from_export)
        # icons：PSD 中无 icon，不导入（encode 只处理 modified 项）

        res = am.encode(out_base)
        for r in res:
            logger.info(f"OUT: {r}")
        return res

    @staticmethod
    def run(ship: str, root: str, face_mode: FaceModeType = FaceModeType.Off, from_export: bool = False) -> list[str]:
        """便捷接口：对 `{root}/{ship}` 船目录执行导入（root 下的工作副本结构），输出到 painting 内。"""
        meta = os.path.join(root, ship, "painting", ship)
        return ImportHelper.run_meta(meta, face_mode=face_mode, from_export=from_export, out_base=os.path.join(root, ship, "painting"))

    @staticmethod
    def run_many(
        meta_paths: list[str],
        face_mode: FaceModeType = FaceModeType.Off,
        from_export: bool = False,
    ) -> dict[str, list[str]]:
        """批量导入（逐船独立 AssetManager，互不影响）。

        meta_paths: 各索引 bundle 的完整路径（任意目录结构，不依赖 {root}/{ship}/painting/{ship} 约定）。
        """
        results = {}
        for meta in meta_paths:
            name = os.path.basename(meta)
            logger.hr(f"Import {name} ({face_mode.name}, from_export={from_export})", 1)
            try:
                results[name] = ImportHelper.run_meta(meta, face_mode=face_mode, from_export=from_export)
            except Exception as e:
                logger.error(f"{name} FAIL: {type(e).__name__}: {e}")
                results[name] = []
        return results

    @staticmethod
    def discover_ships(root: str) -> list[tuple[str, str]]:
        """递归扫描工作根目录，返回 [(索引文件名, 索引完整路径), ...]。

        普适发现：任意深度下的 `painting/` 目录中的无扩展名文件视为索引 bundle
        （不要求目录名 == 索引文件名，不要求 {root}/{ship}/painting/{ship} 结构）。
        """
        ships = []
        if not os.path.isdir(root):
            return ships
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith("output")]  # 不进入输出目录（output / output_off/_auto/_custom）
            if os.path.basename(dirpath) != "painting":
                continue
            for f in sorted(filenames):
                # 排除贴图 bundle（_tex）、变体立绘（_n，与主立绘输出冲突）和带扩展名文件
                if "." in f or f.endswith("_tex") or f.endswith("_n"):
                    continue
                meta = os.path.join(dirpath, f)
                if (f, meta) not in ships:
                    ships.append((f, meta))
        return ships
