# VDODesk 1.1.0 beta 1

<img src="assets/vdodesk-logo.png" alt="VDODesk logo" width="96">

VDODesk is a local-first video editor built with the existing project architecture: a browser UI, a Python standard-library server, and FFmpeg/FFprobe for authoritative media processing. It listens only on `127.0.0.1`, has no account or analytics, and never modifies imported source files.

## Start on macOS (including M4)

1. Install Python 3.10+ and FFmpeg with Homebrew: `brew install python ffmpeg`.
2. Extract the release into a writable folder.
3. Run `./START_MAC.command`, or double-click it if macOS permits.
4. VDODesk opens at <http://127.0.0.1:8765>.

For automatic subject detection, multi-sample tracking, and segmentation masks, run `./INSTALL_ADVANCED_MAC.command` once. This creates a private `.venv` and installs OpenCV. Manual boxes, smart reframe, outlines, and anchored text remain usable without OpenCV.

Windows: install Python and FFmpeg on `PATH`, then run `START_WINDOWS.bat`. Optional OpenCV can be installed with `python -m pip install -r requirements-advanced.txt`.

## Implemented editor features

- Magnetic V1 timeline with numbered video sequencing, drag-to-reorder plus explicit Earlier/Later controls, V2/V3 overlay tracks, source-audio and voiceover lanes; drag either edge to trim, split, duplicate, freeze frame, undo/redo, click/drag scrubbing and frame-step.
- Cross dissolve, fade, wipe, slide and zoom transitions with adjustable duration.
- Crop, overlay positioning/scaling, rotation, zoom, mirror, opacity, stabilization and focal-point controls.
- Brightness, contrast, saturation, gamma, temperature, tint, hue, shadows/highlights and `.cube` 3D LUT support.
- Ten selected-clip filter presets with adjustable intensity: None, Cinematic, Warm, Cool, Vintage, Mono, Noir, Vivid, Soft and Teal & Orange. Filters affect the live preview, preview renders and exports.
- Linear end keyframes for zoom, focal position, color controls and audio gain.
- Subject detection, multi-sample template tracking, GrabCut segmentation mask with manual correction, smart reframing, tracked outline and anchored text. OpenCV activates automated analysis; manual fallback is always available.
- Opening title, text watermark, draggable image watermark, safe-area guides and all five planned aspect-ratio presets.
- Per-clip 0–400% audio gain/mute with animated end level, source audio retention, music mix, adjustable/removable browser-microphone voiceovers and automatic sidechain ducking.
- Audio waveforms, most-recent ten files, low-resolution background proxy generation for large media and browser/GPU-assisted playback.
- Background preview/export jobs, autosave and crash recovery (including a previous-project snapshot), complete workspace asset rediscovery/relinking, JSON project save/open.
- MP4, MOV and WebM containers; H.264, H.265/HEVC and VP9; custom dimensions and quality; Apple VideoToolbox hardware encoding when available with software fallback.

## Workflow

Import media → use `+` to add clips → arrange and trim the timeline → edit the selected clip in the Inspector → use **Render preview** for full compositing → **Export**. Outputs are also retained in `projects/exports/`.

The live browser preview is designed for responsive editing and visibly approximates every color control, crop, keyframes, transforms and animated audio level. **Render preview** and final export use the same FFmpeg project renderer and are the parity reference. Background proxy creation begins automatically for video files larger than 40 MB; reselecting an item after completion makes its proxy available.

## Projects and recovery

- Autosave is kept in the browser's local storage after each edit. Use Inspector → Project → Restore last autosave after a browser or process interruption. Starting a new project also preserves one previous-project recovery snapshot.
- Downloaded `.vdodesk.json` files are portable manifests. Media is stored under `projects/media/`; the editor rediscovers every workspace asset at startup, including items outside Recent 10. Use **Relink selected** if a reference needs replacement.
- The ten most recent imports are stored in `projects/recent-files.json` and survive **New project**.

## Keyboard controls

- Space: play/pause
- Left/Right: one output frame
- Home/End: timeline start/end
- `[` / `]`: selected clip start/end
- Delete/Backspace: delete selected clip
- Command/Ctrl+Z and Command/Ctrl+Shift+Z: undo/redo

## Validation and limitations

Run `python3 -m unittest discover -s tests -v` to exercise workspace persistence, waveforms, proxies, freeze frames, tracking fallbacks, clip filters, color/effect rendering, audio gain/mute, transitions, overlays, titles, watermarks, voiceover ducking and export compatibility. VDODesk is a feature-complete beta, not a signed/notarized macOS application. Very large/high-resolution projects remain bounded by local RAM, storage and FFmpeg performance. Stabilization is FFmpeg `deshake`; tracking uses efficient sampled template tracking rather than a cloud AI service. Test short exports before committing important footage.

Distribution requires an independent review of FFmpeg codec/patent licensing, third-party component licenses, security hardening and Apple notarization requirements.
