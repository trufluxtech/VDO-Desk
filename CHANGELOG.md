# Changelog

## 1.2.1-beta.1

- Fixed independent A1 clips being silent during normal timeline playback.
- Added browser audio players synchronized to the playhead, including seek, pause, timeline start, clip duration, looping and per-item level/mute.
- Reuses browser-compatible proxies for detached source audio when available while retaining FFmpeg as the final render path.

## 1.2.0-beta.1

- Replaced the one-click global music shortcut with editable audio clips on A1.
- Added one-click unlinking of a video clip's source audio while leaving the picture intact.
- Added independent A1 selection, drag positioning, edge trimming, gain, mute, and audio-only deletion.
- Added replacement of selected/unlinked audio with the highlighted imported music file while preserving timeline position and duration.
- Added restoration of the original linked audio after replacement or deletion.
- Added project persistence, relinking, undo/redo, waveform display, and FFmpeg export mixing for independent A1 audio.
- Added an end-to-end render test proving replacement music is exported when the video source audio is detached and muted.

## 1.1.4-beta.1

- Fixed opening titles and text overlays being omitted from completed exports.
- Added a built-in transparent-image text renderer independent of FFmpeg `drawtext` and libass.
- Added dependency-free bitmap-font rendering when Pillow is not installed.
- Applied the fallback to project titles, text watermarks and moving tracked labels.
- Added an end-to-end test that disables every optional FFmpeg text filter and verifies visible exported text.

## 1.1.3-beta.1

- Added direct drag-and-drop clip movement across the video timeline.
- V1 clips now reorder magnetically at the visible insertion point.
- V2/V3 clips move freely with frame snapping and can be dragged between video tracks.
- Added highlighted drop lanes, an insertion marker, drag ghost styling and horizontal edge auto-scroll.
- Fixed pointer capture and timeline-coordinate errors that could prevent a drag from completing after scrolling or rerendering.

## 1.1.2-beta.1

- Fixed `No such filter: drawtext` export failures on affected Homebrew FFmpeg builds.
- Added automatic FFmpeg text-filter detection and a libass fallback for opening titles, text watermarks and tracked labels.
- Export status now reports the selected text renderer and clearly warns if a minimal FFmpeg build cannot render text.

## 1.1.1-beta.1

- Fixed blank/non-playing previews for HEVC/MOV and other browser-incompatible source formats.
- Added codec detection, automatic H.264/AAC preview-proxy creation, readiness polling and playback retry.
- Added visible preview errors instead of silent rejected browser playback promises.
- Added clean Ctrl+C shutdown without a `KeyboardInterrupt` traceback.

## 1.1.0-beta.1

- Added numbered V1 video sequencing with drag-to-reorder and explicit Earlier/Later controls.
- Added nine creative selected-clip filters plus None, with adjustable intensity and live/export parity.
- Added a new transparent VDODesk logo to the app header, favicon, documentation and distribution.
- Added filter-chain regression coverage for every preset.

## 1.0.0-beta.1

- Completed the original 0.4.0 pending-feature implementation in the retained browser/Python/FFmpeg architecture.
- Added V2/V3 overlays, transitions, transforms, crop, stabilization, color tools, LUTs and linear end keyframes.
- Added tracking-assisted reframe, mask preview, outlines, anchored text, freeze frames and optional OpenCV analysis.
- Added waveform display, source-audio mute and 0–400% gain, music mixing, editable voiceovers and fixed sidechain ducking.
- Added continuous playhead scrubbing, boundary/frame navigation, proxies, background jobs, recovery and complete workspace rediscovery/relinking.
- Added MP4/MOV/WebM and H.264/H.265/VP9 export validation with Apple VideoToolbox fallback handling.
- Fixed live-preview feedback for gamma, tint, shadows, highlights and audio end-level controls.
- Expanded the automated suite from four to ten tests, including full FFmpeg integration coverage.

## 0.4.0-beta

- Added Recent 10, a separate source-audio lane, interactive timeline navigation, clip mute and clip-volume controls.
