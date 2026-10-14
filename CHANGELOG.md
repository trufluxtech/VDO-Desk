# Changelog

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
