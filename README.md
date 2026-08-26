# AzurLane Tachie Helper (碧蓝航线立绘助手)

A desktop tool for viewing, decoding, editing and re-packing **Azur Lane** ship
painting assets (tachie / chibi / icons). It turns Unity texture-atlas bundles
back into layered **PSD** documents, lets you paste face expressions
(paintingface) onto paintings and vice versa, crops official icon variants, and
re-encodes modified layers back into the game bundles.

> Based on the open-source project
> [MuteApo/AzurLaneTachieHelper](https://github.com/MuteApo/AzurLaneTachieHelper),
> maintained and improved by **@LeafFairyTales**. For learning and
> communication purposes only; please do not use it for commercial
> distribution.

[简体中文](README.zh-CN.md)

---

## Features

- **Decode to PSD** — rebuild a painting as a layered Photoshop document from
  its texture atlas / bundle (UnityPy based, `FALLBACK_UNITY_VERSION=2022.3.62f3`).
- **Face expression compositing** — paste `paintingface` (差分表情) onto the
  painting, or extract it back; four modes: Off / Auto / Full / Custom.
- **Icon cropping** — crop `shipyardicon` / `herohrzicon` / `squareicon` in
  three steps using the built-in crop box.
- **Encode back** — re-encode edited layer PNGs into game bundles
  (encrypted output to `output_{mode}/`).
- **Batch import / export** — import whole ship folders from PSD or images,
  or export all layers to images (`image_{mode}/`).

## Download & Run

Prebuilt Windows builds are published as GitHub Releases: every tag (e.g.
`1.8.9`) triggers a GitHub Actions build and uploads a `.7z` archive with the
standalone `AzurLaneTachieHelper.exe` — download, extract, run, no Python
required.

Play it with your own game data:

1. `File ▸ Open Metadata` and select a ship's index bundle — an extension-less
   file inside a `painting/` folder.
   > Related assets (paintingface, shipyardicon / herohrzicon / squareicon,
   > dependency textures) are looked up at fixed well-known locations: inside
   > that `painting/` folder or one level up, matching the standard names.

   Example layout (`<data root>`, `xxx` = ship name):

   ```
   data/
   ├── painting/
   │   └── xxx              # extension-less ship index (open this)
   ├── paintingface/
   │   └── xxx
   ├── shipyardicon/
   │   └── xxx
   ├── herohrzicon/
   │   └── xxx
   └── squareicon/
       └── xxx
   ```
2. Decode, edit, re-import, re-encode — see **Workflow** below.

## Workflow

```
Open Metadata (ship index bundle)
  ├─ File ▸ Decode to PSD        → layered PSD for painting, face, icons
  ├─ File ▸ Export Images        → layers as PNGs (image_{off|auto|custom}/)
  │        ▸ Import From Images  → re-import edited PNGs
  ├─ File ▸ Import From PSD      → re-import an edited PSD
  ├─ File ▸ Export && Import     → export all, then import everything back
  └─ File ▸ Import Painting / Paintingface / Icons (single asset targets)
Edit ▸ crop icons             → Clip All / Shipyard / Herohrz / Square Icons
Encode ▸ Encode Texture       → write bundles to output_{off|auto|custom}/
```

### Options (Tools → Option)

- **Paintingface Mode** — how `paintingface` layers are composed onto the
  painting: `Off`, `Auto` (smallest layer), `Full` (largest / full canvas),
  `Custom` (manual expand box).
- **Mesh Decoding Mode** — `rawSpriteSize` (mode 0) vs mesh-deformed size
  (mode 1, for face expressions).
- **Skip Missing** — tolerate missing dependencies / textures / faces instead
  of aborting (default on).
- **Server** — CN / JP / EN region setting.

> Unity uses a y-up coordinate system while image layers use y-down; the tool
> handles the flip internally (`FLIP_TOP_BOTTOM`), PSD output is a normal
> y-down image.

## Build from source

Requirements: Python `>=3.13,<3.14`, [uv](https://docs.astral.sh/uv/).

```bash
uv sync --python 3.13      # install dependencies (pytoshop comes from its git
                           # source and compiles the native packbits extension)
uv run python app.py       # launch the GUI
```

Packaging (GitHub Actions, `.github/workflows/build.yml`):

- Triggered automatically by pushing a tag matching `*.*.*`, or manually via
  `workflow_dispatch`.
- Produces a standalone `AzurLaneTachieHelper.exe` plus all data files
  (including the `rich` unicode cell tables needed at runtime and the compiled
  `i18n/zh_CN.qm` translation).

## Tech stack

Python 3.13 · PySide6 (Qt6) + qdarktheme · UnityPy · pytoshop (native packbits)
· Pillow / NumPy · rich · uv.

## License & Notice

This tool is for learning and communication only. Please do not distribute it
commercially or use it for profit. See the startup notice inside the app for
details.