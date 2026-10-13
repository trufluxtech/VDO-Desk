# VDODesk 1.0.0 beta 1 scope and implementation map

The original roadmap is implemented in the retained local Python/browser/FFmpeg architecture.

| Planned capability | Implementation |
|---|---|
| Magnetic multi-track timeline | Magnetic V1 sequencing plus independently timed V2/V3 overlays, audio and voiceover lanes |
| Drag trim and transitions | Pointer edge trimming; dissolve, fade, wipe, slide and zoom FFmpeg transitions |
| Advanced transforms/effects | Crop, position, rotate, zoom, mirror, opacity, stabilization and animated end keyframes |
| Color controls | White balance, tint, hue, gamma, shadows/highlights, saturation/contrast/brightness and `.cube` LUTs |
| Safe area and smart reframe | Safe-area overlay plus tracked focal points driving animated `zoompan` framing |
| Tracking, masks and outlines | OpenCV detection/GrabCut, manual correction, sampled template path, outline and anchored text; dependency-free fallback |
| Freeze frame and voiceover | FFmpeg still extraction, MediaRecorder capture, timed VO lane and sidechain ducking |
| Proxy/GPU/background work | Automatic proxy jobs, browser-accelerated playback, background preview/export, VideoToolbox encode detection |
| Recovery and relinking | Browser autosave plus previous-project recovery, downloadable project manifests, complete workspace rediscovery and reference replacement across a project |
| Export expansion | MP4/MOV/WebM, H.264/H.265/VP9, custom even dimensions, quality and hardware/software selection |
| Recent files and clip audio | Persistent last ten imports, waveform lane, mute, animated 0–400% live/export gain and editable voiceovers |

Beta 1 also fixes the complete sidechain graph used by voiceover ducking, groups inspector gestures into undoable edits, makes ruler scrubbing continuously draggable, constrains crop recipes, and prevents invalid WebM/MP4/MOV codec combinations.

## Architecture boundary

The requested architecture retention intentionally excludes a native Qt/C++ rewrite and signed `.app`/Windows binary. The supplied launchers run the local Python service and browser editor. FFmpeg remains authoritative for previews and exports, with feature detection selecting Apple VideoToolbox where available.
