"""Live2D bundle 解包与标准模型组装（模块内业务，不引用其它模块）。

流程：extract() 从 Unity AssetBundle 解出 moc3 + 贴图 PNG；
materialize() 落盘为标准 Live2D 模型目录（model3.json 自动生成，物理使用
moc3 内嵌数据）；with_motions() 把 bundle 内 AnimationClip 转成
motions/*.motion3.json 并更新 model3.json；prepare_web() 把渲染页面
（index.html + JS）复制进模型目录，预览模块用本地 HTTP 服务直接加载。
"""
import io
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field

import UnityPy
from UnityPy.enums import ClassIDType

from .anim import AnimationExporter

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


@dataclass
class Live2DModelBundle:
    """从 bundle 解出的 Live2D 模型数据。"""

    name: str
    moc3: bytes = b""
    textures: list[bytes] = field(default_factory=list)  # PNG bytes，顺序即贴图索引
    physics3: bytes | None = None  # 物理解析 JSON 变体（可选，二期接入标准 physics3）


class Live2DHelper:
    @staticmethod
    def extract(bundle_path: str) -> Live2DModelBundle:
        """从 Unity AssetBundle 解出 Live2D 模型。

        - moc3：CubismMoc 资产（MonoBehaviour）的 `_bytes` 字段，签名 "MOC3"；
        - 贴图：全部 Texture2D（PNG，顺序 = 模型贴图索引）；
        - physics3：TextAsset 中 JSON 结构（Version>=3 且含 PhysicsSettings）的变体，暂存备用。
        """
        env = UnityPy.load(bundle_path)
        moc3: bytes | None = None
        textures: list[bytes] = []
        physics3: bytes | None = None
        tex_infos: list[tuple[str, bytes]] = []  # (m_Name, PNG bytes)
        for obj in env.objects:
            if obj.type == ClassIDType.MonoBehaviour:
                try:
                    d = obj.read_typetree()
                except Exception:
                    continue
                raw = d.get("_bytes")
                if isinstance(raw, list) and raw and bytes(raw[:4]) == b"MOC3":
                    moc3 = bytes(raw)  # moc3 本体（几 MB 级二进制）
            elif obj.type == ClassIDType.TextAsset:
                data = Live2DHelper._read_bytes(obj)
                if data[:1] == b"{" and b"PhysicsSettings" in data[:512]:
                    physics3 = data  # 物理解析 JSON 变体
            elif obj.type == ClassIDType.Texture2D:
                try:
                    meta = obj.read_typetree()
                    tex = obj.parse_as_object()
                    img = tex.image
                    if img is not None:
                        buf = io.BytesIO()
                        img.convert("RGBA").save(buf, format="PNG")
                        tex_infos.append((meta.get("m_Name", "") or "", buf.getvalue()))
                except Exception:
                    continue  # 单张贴图解码失败跳过（Skip Missing 精神）
        if moc3 is None:
            raise ValueError("No moc3 (MOC3-signed bytes) found in bundle")
        # 贴图顺序必须与模型纹理索引一致：按 m_Name 自然排序（texture_00/texture_01 → 主图在前）
        textures = [png for _, png in sorted(tex_infos, key=lambda x: Live2DHelper._nat_key(x[0]))]
        name = os.path.splitext(os.path.basename(bundle_path))[0]
        return Live2DModelBundle(name=name, moc3=moc3, textures=textures, physics3=physics3)

    @staticmethod
    def _nat_key(text: str) -> list:
        """自然排序键：'texture_00' < 'texture_01' < 'texture_10'（数字按数值）。"""
        import re

        return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]

    @staticmethod
    def _read_bytes(obj) -> bytes:
        """typetree 的 m_Script 可能是 str（latin-1 映射）或 bytes。"""
        d = obj.read_typetree()
        script = d.get("m_Script", b"") or b""
        if isinstance(script, str):
            try:
                return script.encode("latin-1")
            except UnicodeEncodeError:
                return script.encode("utf-8")
        return bytes(script)

    @staticmethod
    def materialize(bundle: Live2DModelBundle, root: str | None = None) -> tuple[str, str]:
        """落盘标准模型目录，返回 (dir, model3 文件名)。模型物理走 moc3 内嵌。"""
        model_dir = root or tempfile.mkdtemp(prefix="alth_live2d_")
        os.makedirs(os.path.join(model_dir, "textures"), exist_ok=True)

        moc3_name = f"{bundle.name}.moc3"
        with open(os.path.join(model_dir, moc3_name), "wb") as f:
            f.write(bundle.moc3)

        tex_paths = []
        for i, png in enumerate(bundle.textures):
            tex_name = f"texture_{i:02d}.png"
            with open(os.path.join(model_dir, "textures", tex_name), "wb") as f:
                f.write(png)
            tex_paths.append(f"textures/{tex_name}")

        model3 = {
            "Version": 3,
            "Name": bundle.name,
            "FileReferences": {"Moc": moc3_name, "Textures": tex_paths},
            "Groups": [],
        }
        if bundle.physics3:
            with open(os.path.join(model_dir, f"{bundle.name}.physics3.json"), "wb") as f:
                f.write(bundle.physics3)
            model3["FileReferences"]["Physics"] = f"{bundle.name}.physics3.json"
        model3_name = f"{bundle.name}.model3.json"
        with open(os.path.join(model_dir, model3_name), "w", encoding="utf-8") as f:
            json.dump(model3, f, ensure_ascii=False, indent=2)
        return model_dir, model3_name

    @staticmethod
    def prepare_web(model_dir: str, model3_name: str) -> None:
        """把渲染页面（index.html + 三个 JS）复制进模型目录，模型名填入模板。"""
        os.makedirs(model_dir, exist_ok=True)
        for js in (
            "pixi.min.js",
            "live2d.min.js",
            "live2dcubismcore.min.js",
            "pixi-live2d-display.min.js",
        ):
            src = os.path.join(WEB_DIR, js)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(model_dir, js))
        if os.path.exists(WEB_DIR):
            shutil.copy2(os.path.join(WEB_DIR, "index.template.html"), os.path.join(model_dir, "index.html"))
        html_path = os.path.join(model_dir, "index.html")
        with open(html_path, encoding="utf-8") as f:
            html = f.read()
        html = html.replace("__MODEL3__", model3_name)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

    @staticmethod
    def with_motions(model_dir: str, model3_name: str, bundle_path: str) -> list[str]:
        """从 bundle 解出全部 AnimationClip → motions/*.motion3.json，更新 model3.json 引用。

        返回动作名列表（无动作返回空）。
        """
        exporter = AnimationExporter(bundle_path)
        motions = exporter.extract_all()
        if not motions:
            return []
        os.makedirs(os.path.join(model_dir, "motions"), exist_ok=True)
        names = sorted(motions.keys())
        for name in names:
            with open(os.path.join(model_dir, "motions", f"{name}.motion3.json"), "w", encoding="utf-8") as f:
                json.dump(motions[name], f, ensure_ascii=False, indent=2)
        m3_path = os.path.join(model_dir, model3_name)
        with open(m3_path, encoding="utf-8") as f:
            m3 = json.load(f)
        m3["FileReferences"]["Motions"] = {name: [{"File": f"motions/{name}.motion3.json"}] for name in names}
        with open(m3_path, "w", encoding="utf-8") as f:
            json.dump(m3, f, ensure_ascii=False, indent=2)
        return names

    @staticmethod
    def cleanup(model_dir: str | None):
        """删除解包临时目录。"""
        if model_dir and os.path.isdir(model_dir):
            shutil.rmtree(model_dir, ignore_errors=True)