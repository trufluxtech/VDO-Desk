# VDODesk 1.5.0 beta 1 scope and implementation map

The original roadmap is implemented in the retained local Python/browser/FFmpeg architecture.

| Planned capability | Implementation |
|---|---|
| Magnetic multi-track timeline | Numbered magnetic V1 sequencing with direct drag-and-drop reordering; freely timed V2/V3 clips can be dragged horizontally or between video tracks, with visible drop targets and edge auto-scroll |
| Drag trim and transitions | Pointer edge trimming; dissolve, fade, wipe, slide and zoom FFmpeg transitions |
| Advanced transforms/effects | Crop, position, rotate, zoom, mirror, opacity, stabilization and animated end keyframes |
| Color controls | White balance, tint, hue, gamma, shadows/highlights, saturation/contrast/brightness and `.cube` LUTs |
| Selected-clip filters | Ten presets with adjustable intensity and matching live-preview/FFmpeg export behavior |
| Stickers and emoji | Dedicated S1 track with built-in emoji, imported image stickers, drag/trim timing, direct viewer placement, transforms, persistence, relinking and FFmpeg export |
| 3D photo movement | Local depth generation, five camera presets, live 2.5D preview, focal/radius correction, imported custom depth maps and depth-separated FFmpeg export |
| Compact editing navigation | Categorized Inspector Tool drop-down covering all clip, transform, color, filter, motion, audio, layer, analysis, project and export panels |
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

Version 1.3.0 beta 1 packages the same editor for Windows 10 and 11. Its launcher detects supported Python installations and project virtual environments, validates both FFmpeg executables, handles paths containing spaces and retains terminal errors. Separate helpers install the core prerequisites with Windows Package Manager and optional OpenCV into an isolated environment.

Version 1.4.0 beta 1 adds the S1 sticker layer. Native emoji are converted in the browser to transparent PNG media, while imported PNG, JPEG and WebP images can also be used. Every sticker has independent timing, position, scale, rotation and opacity in live preview and FFmpeg export, with timeline drag/trim, direct viewer dragging, save/recovery, undo/redo and relinking support.

Version 1.5.0 beta 1 adds 3D Photo Motion without changing the local architecture. It creates a soft subject depth map locally, moves foreground and background through independent camera paths, and uses the same depth-separated compositor for rendered previews and final exports. OpenCV improves automatic subject separation when present; the built-in focal-depth fallback and custom grayscale depth-map option keep the feature functional on clean macOS and Windows installations. The Inspector is consolidated into one categorized Tool drop-down to reduce visual clutter.

## Architecture boundary

The requested architecture retention intentionally excludes a native Qt/C++ rewrite and signed `.app`/Windows installer. The supplied Windows and macOS launchers run the local Python service and browser editor. FFmpeg remains authoritative for previews and exports, with feature detection selecting Apple VideoToolbox where available.
