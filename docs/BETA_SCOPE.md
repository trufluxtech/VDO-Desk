# VDODesk 1.2.1 beta 1 scope and implementation map

The original roadmap is implemented in the retained local Python/browser/FFmpeg architecture.

| Planned capability | Implementation |
|---|---|
| Magnetic multi-track timeline | Numbered magnetic V1 sequencing with direct drag-and-drop reordering; freely timed V2/V3 clips can be dragged horizontally or between video tracks, with visible drop targets and edge auto-scroll |
| Drag trim and transitions | Pointer edge trimming; dissolve, fade, wipe, slide and zoom FFmpeg transitions |
| Advanced transforms/effects | Crop, position, rotate, zoom, mirror, opacity, stabilization and animated end keyframes |
| Color controls | White balance, tint, hue, gamma, shadows/highlights, saturation/contrast/brightness and `.cube` LUTs |
| Selected-clip filters | Ten presets with adjustable intensity and matching live-preview/FFmpeg export behavior |
| Safe area and smart reframe | Safe-area overlay plus tracked focal points driving animated `zoompan` framing |
| Tracking, masks and outlines | OpenCV detection/GrabCut, manual correction, sampled template path, outline and anchored text; dependency-free fallback |
| Freeze frame and voiceover | FFmpeg still extraction, MediaRecorder capture, timed VO lane and sidechain ducking |
| Proxy/GPU/background work | Automatic proxy jobs, browser-accelerated playback, background preview/export, VideoToolbox encode detection |
| Recovery and relinking | Browser autosave plus previous-project recovery, downloadable project manifests, complete workspace rediscovery and reference replacement across a project |
| Export expansion | MP4/MOV/WebM, H.264/H.265/VP9, custom even dimensions, quality and hardware/software selection |
| Recent files and clip audio | Persistent last ten imports, waveform lane, mute, animated 0–400% live/export gain, unlinkable A1 audio, audio-only deletion, selected-music replacement and editable voiceovers |

Version 1.1 beta 1 adds explicit video sequencing controls, numbered timeline clips, selected-clip filter presets and the new VDODesk application logo. It retains the sidechain, undo grouping, continuous ruler scrubbing, crop constraints and export compatibility fixes from version 1.0 beta 1.

Version 1.1.1 beta 1 fixes browser preview playback for HEVC/MOV and other unsupported source formats by detecting codecs, generating H.264/AAC proxies automatically, polling until the proxy is ready, and retrying playback. Terminal shutdown with Ctrl+C now exits without a Python traceback.

Version 1.1.2 beta 1 fixes export failures on FFmpeg builds without the optional `drawtext` filter. Titles, text watermarks and tracked labels automatically use the compatible libass renderer when necessary.

Version 1.1.3 beta 1 makes timeline clip movement a direct drag-and-drop interaction. V1 clips reorder magnetically, V2/V3 clips move freely with frame snapping, and clips can be moved between video tracks using highlighted drop targets.

Version 1.1.4 beta 1 guarantees text export even when FFmpeg provides neither `drawtext` nor libass. VDODesk renders opening titles, watermarks and tracked labels to transparent images and composites them with the standard video overlay filter. A dependency-free embedded bitmap font remains available when Pillow is not installed.

Version 1.2.0 beta 1 replaces the old project-music shortcut with true A1 editing. Source audio can be unlinked from video, selected and deleted independently, replaced with a highlighted music file, dragged or trimmed on A1, and restored to the original linked state. Independent audio is persisted, relinked, mixed into preview renders and final exports, and included in undo/redo.

Version 1.2.1 beta 1 adds synchronized browser playback for independent A1 audio. Timeline Play now starts, seeks, pauses and loops A1 items at their actual timeline positions, with live mute and level control; FFmpeg remains authoritative for rendered previews and exports.

## Architecture boundary

The requested architecture retention intentionally excludes a native Qt/C++ rewrite and signed `.app`/Windows binary. The supplied launchers run the local Python service and browser editor. FFmpeg remains authoritative for previews and exports, with feature detection selecting Apple VideoToolbox where available.
