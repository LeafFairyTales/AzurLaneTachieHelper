# AzurLane Tachie Helper（碧蓝航线立绘助手）

一款用于查看、解码、编辑并回编**碧蓝航线**立绘资源（tachie / 差分表情 / 图标）的桌面工具。它能把 Unity 纹理图集（Texture Atlas / bundle）还原成带图层的 **PSD** 文档，支持把差分表情（paintingface）贴到立绘上或反向导回、裁剪三种官方图标，并把修改后的图层重新编码写回游戏 bundle。

> 基于开源项目
> [MuteApo/AzurLaneTachieHelper](https://github.com/MuteApo/AzurLaneTachieHelper)
> 修改优化，由 **@LeafFairyTales** 完善维护。本工具仅供学习交流使用，请勿传播或用于商业用途。

[English](README.md)

---

## 功能特性

- **解码为 PSD** — 从纹理图集 / bundle 将立绘还原成带图层的 Photoshop 文档（UnityPy 解析，`FALLBACK_UNITY_VERSION=2022.3.62f3`）。
- **差分表情合成** — 将 `paintingface`（差分表情）贴到立绘上，或反向提取；四种模式：关闭 / 自动 / 完整 / 自定义。
- **图标裁剪** — 使用内置裁剪框分步裁剪 `shipyardicon` / `herohrzicon` / `squareicon` 三种图标。
- **回编 bundle** — 将修改后的图层 PNG 重新编码写回游戏 bundle（加密输出到 `output_{模式}/` 目录）。
- **批量导入 / 导出** — 从 PSD 或图片批量导入整船目录，或导出全部图层为图片（`image_{模式}/`）。

## 下载与运行

Windows 构建产物通过 GitHub Releases 发布：每次打 tag（例如 `1.8.9`）都会触发 GitHub Actions 自动构建并上传 `.7z` 压缩包，内含独立的 `AzurLaneTachieHelper.exe` —— 解压即可运行，无需安装 Python。

使用你自己的游戏数据：

1. `文件 ▸ 打开元数据`，选择一个舰船索引 bundle —— 即 `painting/` 目录下的无扩展名文件。
   > 提示：关联资产（paintingface、shipyardicon / herohrzicon / squareicon、依赖贴图）按固定路径查找 —— 索引所在 `painting/` 目录内，或上一级目录，匹配标准命名。

   示例目录结构（`<数据根>`，`xxx` = 船名）：

   ```
   data/
   ├── painting/
   │   └── xxx              # 无扩展名，舰船索引（打开它）
   ├── paintingface/
   │   └── xxx
   ├── shipyardicon/
   │   └── xxx
   ├── herohrzicon/
   │   └── xxx
   └── squareicon/
       └── xxx
   ```
2. 解码、编辑、重新导入、回编 —— 详见下方**工作流**。

## 工作流

```
打开元数据（舰船索引 bundle）
  ├─ 文件 ▸ 解码为 PSD              → 立绘 / 差分表情 / 图标的带图层 PSD
  ├─ 文件 ▸ 导出图片                → 图层 PNG（image_{off|auto|custom}/）
  │        ▸ 从图片导入              → 重新导入编辑后的 PNG
  ├─ 文件 ▸ 从 PSD 导入              → 重新导入编辑后的 PSD
  ├─ 文件 ▸ 导出并导入              → 先全部导出，再全部导入
  └─ 文件 ▸ 导入立绘图层 / 导入表情差分 / 导入图标（单资源导入）
编辑 ▸ 裁剪图标                  → 裁剪全部 / 船坞 / 横版 / 方形图标
封包立绘                        → 写回 bundle 到 output_{off|auto|custom}/
```

### 选项（选项菜单）

- **高拆模式（Paintingface Mode）** — 决定 `paintingface` 图层如何贴到立绘：`关闭`、`自动`（最小图层）、`完整`（最大图层 / 整图）、`自定义`（手动扩展框）。
- **网格解码模式（Mesh Decoding Mode）** — `rawSpriteSize`（模式 0）与网格变形尺寸（模式 1，用于差分表情）。
- **跳过缺失（Skip Missing）** — 遇到缺失依赖 / 贴图 / 表情时跳过继续而非中断（默认开启）。
- **区服（Server）** — B服 / 日服 / 国际服。

> 说明：Unity 坐标 y 向上，图层图像 y 向下，工具内部已统一处理坐标翻转（`FLIP_TOP_BOTTOM`），PSD 输出为正像。

## 从源码构建

环境要求：Python `>=3.13,<3.14`，[uv](https://docs.astral.sh/uv/)。

```bash
uv sync --python 3.13      # 安装依赖（pytoshop 来自 git 源，自动编译原生 packbits 扩展）
uv run python app.py       # 启动图形界面
```

打包（GitHub Actions，`.github/workflows/build.yml`）：

- 推送匹配 `*.*.*` 的 tag 自动触发，或通过 `workflow_dispatch` 手动触发；
- 产出独立的 `AzurLaneTachieHelper.exe` 及全部数据文件（含运行时所需的 rich unicode 数据表与编译好的 `i18n/zh_CN.qm` 中文本地化）。

## 技术栈

Python 3.13 · PySide6（Qt6）+ qdarktheme · UnityPy · pytoshop（原生 packbits）· Pillow / NumPy · rich · uv

## 许可与声明

本工具仅供学习交流使用，请勿用于商业传播或盈利。详见应用启动时的版权声明。