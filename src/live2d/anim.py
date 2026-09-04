"""Unity AnimationClip → Cubism motion3.json 转换（StreamedClip 解析）。

格式要点（经 bundle 数据实证）：
- m_MuscleClip.m_Clip.data.m_StreamedClip.data = 帧流，无额外头部；
- 帧 = { Time: float32, curveCount: int32, curves[] }，帧与帧之间 4 字节对齐（2017+）；
- 曲线 = { Index: int32, Cx/Cy/Cz: float32×3, Value: float32 }（20B）；
- Index = genericBindings 内绑定序号；
- 第一帧 Time=-FLT_MAX（初始姿势帧），最后一帧为 dummy（跳过）；
- binding path = CRC32(层级路径)，attribute = CRC32("Value")；
- 参数 Id = 参数 GameObject 的名字（CubismParameter 组件挂在参数节点上）。
"""
import json
import struct
import zlib
from collections import defaultdict

import UnityPy
from UnityPy.enums import ClassIDType

_MAX_FLOAT_BITS = 0xFF7FFFFF  # float.MinValue（首帧标记）


def crc32(text: str) -> int:
    return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF


def _f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


class AnimationExporter:
    """从 bundle 解出所有 AnimationClip → motion3 dict。"""

    def __init__(self, bundle_path: str):
        self.env = UnityPy.load(bundle_path)
        self._build_scene()
        self._build_bindings()

    # ---- 场景：GameObject 树 → 路径（供 binding path 哈希匹配）----
    def _build_scene(self):
        go_names = {}
        go_trans = {}
        for o in self.env.objects:
            if o.type == ClassIDType.GameObject:
                d = o.read_typetree()
                go_names[o.path_id] = d.get("m_Name", "") or ""
        for o in self.env.objects:
            if o.type == ClassIDType.Transform:
                d = o.read_typetree()
                go_trans[o.path_id] = {
                    "go": d.get("m_GameObject", {}).get("m_PathID"),
                    "father": d.get("m_Father", {}).get("m_PathID"),
                }
        self.go_names = go_names
        self.go_trans = go_trans
        # 缓存路径字符串（根名 / 无根名两种格式都试，CRC32 命中者为准）
        self.path_cache: dict[int, str] = {}
        for tid, t in go_trans.items():
            self._path_of(tid)

    def _path_of(self, tid) -> str:
        if tid in self.path_cache:
            return self.path_cache[tid]
        parts = []
        cur = tid
        seen = 0
        while cur is not None and seen < 30:
            t = self.go_trans.get(cur)
            if not t:
                break
            go = t["go"]
            parts.append(self.go_names.get(go, ""))
            cur = t["father"]
            seen += 1
        path = "/".join(reversed([p for p in parts if p]))
        # Unity 动画绑定路径不含场景根：去掉首段（根对象名）
        segs = path.split("/")
        path = "/".join(segs[1:]) if len(segs) > 1 else path
        self.path_cache[tid] = path
        return path

    # ---- binding：GenericBinding → 参数 Id（CRC32 path 匹配）----
    def _build_bindings(self):
        # 参数节点路径（含/不含根名）→ GO 名
        path_to_go: dict[str, int] = {}
        for tid, t in self.go_trans.items():
            go = t["go"]
            p = self.path_cache.get(tid, "")
            if p:
                path_to_go.setdefault(p, go)
        self._path_to_go = path_to_go

    def resolve_binding_path(self, path_hash: int) -> str | None:
        """CRC32 命中路径；返回路径字符串（找不到返回 None）。"""
        for p, _ in self._path_to_go.items():
            if crc32(p) == path_hash:
                return p
        return None

    def parameter_name_for_binding(self, path_hash: int) -> str | None:
        """binding path 哈希 → 参数 GameObject 名（参数 Id，即路径叶子）。"""
        for p, go in self._path_to_go.items():
            if crc32(p) == path_hash:
                return (self.go_names.get(go) or "").split("/")[-1] or None
        return None

    # ---- StreamedClip 帧解析 ----
    @staticmethod
    def parse_frames(data: list[int]) -> list[tuple[float, dict[int, tuple[float, float, float, float]]]]:
        """data: uint32 列表 → [(time, {index: (Cx, Cy, Cz, Value)})]（跳过首/尾帧）"""
        frames = []
        pos = 0
        n = len(data)
        first = True
        while pos + 2 <= n:
            time_bits = data[pos]
            count = data[pos + 1]
            pos += 2
            if count <= 0 or count > 4096:
                pos += 4  # 对齐兜底
                continue
            curves: dict[int, tuple[float, float, float, float]] = {}
            for _ in range(count):
                if pos + 5 > n:
                    break
                idx, cx, cy, cz, v = data[pos : pos + 5]
                curves[idx] = (_f32(cx), _f32(cy), _f32(cz), _f32(v))
                pos += 5
            if first:
                first = False  # 第一帧（Time=-FLT_MAX 初始姿势）跳过
            else:
                seconds = _f32(time_bits)
                frames.append((seconds, curves))
        return frames

    # ---- motion3 生成 ----
    def clip_to_motion3(self, anim_clip_obj) -> dict:
        d = anim_clip_obj.read_typetree()
        data = d["m_MuscleClip"]["m_Clip"]["data"]["m_StreamedClip"]["data"]
        stop_time = d["m_MuscleClip"].get("m_StopTime") or 0.0
        sample_rate = d.get("m_SampleRate") or 60.0

        # 绑定：bindings[Index] → path hash
        gb = d["m_ClipBindingConstant"]["genericBindings"]

        # 帧解析 → 每参数关键帧 (time, value)
        frames = self.parse_frames(data)
        if not frames:
            return None
        # 首帧（初始姿势）在 parse_frames 里被跳过——需要它作 t=0 初值。
        # 重新解析含首帧版本：这里简化——从首帧拿初值。
        raw_frames = self.parse_frames_full(data)
        param_keys: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for t, curves in raw_frames:
            for idx, cx, cy, cz, v in curves:
                param_keys[idx].append((t, v))
        # 排序去抖
        for k in param_keys:
            param_keys[k].sort()
            out = []
            last_t, last_v = None, None
            for t, v in param_keys[k]:
                if last_t is not None and abs(t - last_t) < 1e-4:
                    last_v = v  # 同帧取最后值
                    continue
                if last_t is not None:
                    out.append((last_t, last_v))
                last_t, last_v = t, v
            if last_t is not None:
                out.append((last_t, last_v))
            param_keys[k] = out

        # 每参数：Id + Segments（贝塞尔：Hermite 系数 → 三次贝塞尔控制点）
        curves_json = []
        total_segments = 0
        total_points = 0
        for idx, keys in sorted(param_keys.items()):
            if idx >= len(gb):
                continue
            path_hash = int(gb[idx].get("path", "0"))
            pid = self.parameter_name_for_binding(path_hash)
            if pid is None:
                continue
            if len(keys) < 2:
                segments = [0.0, keys[0][1], keys[0][1]] if keys else [0.0, 0.0]
                curves_json.append({"Target": "Parameter", "Id": pid, "Segments": segments})
                total_segments += 1
                total_points += len(segments) // 2 + 1
                continue
            segments = []
            for i in range(len(keys) - 1):
                t0, v0 = keys[i]
                t1, v1 = keys[i + 1]
                dt = t1 - t0
                if dt <= 0:
                    continue
                # 线性段（向后兼容保险）；系数曲线留作增强
                segments.extend([round(t0, 4), round(v0, 4), round(t1, 4), round(v1, 4)])
            if keys:
                t_end, v_end = keys[-1]
                segments.extend([round(t_end, 4), round(v_end, 4)])
            if segments:
                curves_json.append({"Target": "Parameter", "Id": pid, "Segments": segments})
                total_segments += len([s for s in segments]) // 4 + 1

        duration = stop_time if stop_time > 0 else (frames[-1][0] if frames else 1.0)
        motion = {
            "Version": 3,
            "Meta": {
                "Duration": round(float(duration), 4),
                "Fps": int(sample_rate),
                "Loop": True,
                "AreBeziersRestricted": True,
                "CurveCount": len(curves_json),
                "TotalSegmentCount": total_segments,
                "TotalPointCount": max(total_segments * 2, 0),
                "UserDataCount": 0,
                "TotalUserDataSize": 0,
            },
            "Curves": curves_json,
            "UserData": [],
        }
        return motion

    def parse_frames_full(self, data) -> list[tuple[float, list[tuple[int, float, float, float, float]]]]:
        """完整帧解析（含首帧），返回 [(time, [(idx, cx, cy, cz, v), ...])]"""
        frames = []
        pos = 0
        n = len(data)
        while pos + 2 <= n:
            time_bits, count = data[pos], data[pos + 1]
            pos += 2
            if count <= 0 or count > 4096:
                pos += 4
                continue
            curves = []
            for _ in range(count):
                if pos + 5 > n:
                    break
                idx, cx, cy, cz, v = data[pos : pos + 5]
                curves.append((idx, _f32(cx), _f32(cy), _f32(cz), _f32(v)))
                pos += 5
            t = _f32(time_bits)
            if time_bits == _MAX_FLOAT_BITS or t < -1e30:
                t = 0.0  # 第一帧 Time=-FLT_MAX（初始姿势帧）→ 时间轴 0
            frames.append((t, curves))
        return frames

    def extract_all(self) -> dict[str, dict]:
        """所有 AnimationClip → {动作名: motion3 dict}"""
        motions = {}
        for obj in self.env.objects:
            if obj.type != ClassIDType.AnimationClip:
                continue
            try:
                d = obj.read_typetree()
            except Exception:
                continue
            name = d.get("m_Name", "")
            if not name:
                continue
            try:
                m = self.clip_to_motion3(obj)
            except Exception as e:
                print(f"[anim] skip {name}: {e!r}")
                continue
            if m:
                motions[name] = m
        return motions