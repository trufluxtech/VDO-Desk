from array import array
import copy
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
import render_engine


class RenderEngineTests(unittest.TestCase):
    @staticmethod
    def decoded_frame_digest(path, at=0.2):
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(at),
            "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ], check=True, capture_output=True)
        return hashlib.sha256(result.stdout).hexdigest()

    @staticmethod
    def decoded_audio_rms(path):
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
            "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1",
        ], check=True, capture_output=True)
        samples = array("h"); samples.frombytes(result.stdout)
        return (sum(value * value for value in samples) / max(1, len(samples))) ** .5

    def test_dimensions_and_tempo_chaining(self):
        self.assertEqual((1080, 1920), render_engine.output_dimensions({"ratio": "9:16"}))
        self.assertEqual((638, 358), render_engine.output_dimensions({"export": {"width": 639, "height": 359}}))
        self.assertEqual(["atempo=2", "atempo=2.000000"], render_engine.atempo_filters(4))

    def test_export_container_and_codec_are_compatible(self):
        capabilities = {}
        self.assertEqual(("webm", "vp9", "libvpx-vp9"),
                         render_engine.final_codec({"export": {"container": "webm", "codec": "h264"}}, capabilities))
        self.assertEqual(("mp4", "h264", "libx264"),
                         render_engine.final_codec({"export": {"container": "mp4", "codec": "vp9"}}, capabilities))
        self.assertEqual(("mp4", "h264", "libx264"),
                         render_engine.final_codec({"export": {"container": "invalid", "codec": "invalid"}}, capabilities))

    def test_text_renderer_prefers_drawtext_then_libass(self):
        self.assertEqual("drawtext", render_engine.text_renderer({"drawtext": True, "ass": True}))
        self.assertEqual("libass", render_engine.text_renderer({"drawtext": False, "ass": True}))
        self.assertEqual("builtin-image", render_engine.text_renderer({}))

    def test_all_clip_filter_presets_build_ffmpeg_chains(self):
        presets = {"cinematic", "warm", "cool", "vintage", "mono", "noir", "vivid", "soft", "teal_orange"}
        for preset in presets:
            with self.subTest(preset=preset):
                self.assertTrue(render_engine.clip_filter_chain({"filter": preset, "filterIntensity": .65}))
        self.assertEqual([], render_engine.clip_filter_chain({"filter": "none", "filterIntensity": 1}))
        self.assertEqual([], render_engine.clip_filter_chain({"filter": "vivid", "filterIntensity": 0}))
        self.assertEqual([], render_engine.clip_filter_chain({"filter": "untrusted", "filterIntensity": 1}))

    def test_all_photo_motion_presets_build_camera_paths(self):
        for preset in {"push-in", "pull-out", "orbit-left", "orbit-right", "floating-portrait"}:
            with self.subTest(preset=preset):
                background, foreground = render_engine.photo_motion_expressions({
                    "preset": preset, "depthStrength": .8, "travel": .09,
                    "focusX": .5, "focusY": .45, "edgeFill": 1.08,
                    "easing": "ease-in-out",
                }, 30)
                self.assertEqual({"z", "x", "y"}, set(background))
                self.assertEqual({"z", "x", "y"}, set(foreground))
                self.assertNotEqual(background, foreground)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_all_clip_filter_presets_execute_in_ffmpeg(self):
        presets = {"cinematic", "warm", "cool", "vintage", "mono", "noir", "vivid", "soft", "teal_orange"}
        for preset in presets:
            with self.subTest(preset=preset):
                chain = render_engine.clip_filter_chain({"filter": preset, "filterIntensity": .65})
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=64x36:rate=5:duration=0.2", "-vf", ",".join(chain),
                    "-frames:v", "1", "-f", "null", "-",
                ], check=True, capture_output=True)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_real_render_applies_edits_and_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "testsrc2=size=160x90:rate=20:duration=0.8", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=48000:duration=0.8", "-shortest", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], check=True)
            clip = {
                "file": source.name, "track": 0, "start": 0, "end": .7, "speed": 1,
                "volume": .7, "brightness": .08, "contrast": 1.1, "saturation": 1.2,
                "crop": {"x": 0, "y": 0, "w": 1, "h": 1}, "zoom": 1.05,
                "focusX": .5, "focusY": .5, "keyframes": {"zoomEnd": 1.15},
            }
            spec = {
                "ratio": "16:9", "fps": 20, "clips": [clip],
                "export": {"container": "mp4", "codec": "h264", "width": 320, "height": 180, "hardware": False, "quality": 30},
            }
            output, details = render_engine.render_project("unit", spec, root, root, lambda *_: None)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1000)
            self.assertEqual("libx264", details["codec"])
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(output),
            ], check=True, capture_output=True, text=True).stdout
            self.assertIn('"width": 320', probe)
            self.assertIn('"codec_type": "audio"', probe)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_visual_controls_and_clip_mute_change_rendered_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "testsrc2=size=160x90:rate=20:duration=0.8", "-f", "lavfi", "-i",
                "sine=frequency=660:sample_rate=48000:duration=0.8", "-shortest", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], check=True)
            base_clip = {"file": source.name, "track": 0, "start": 0, "end": .7, "speed": 1,
                         "volume": 1, "crop": {"x": 0, "y": 0, "w": 1, "h": 1}}
            base_spec = {"ratio": "16:9", "fps": 20, "clips": [base_clip],
                         "export": {"container": "mp4", "codec": "h264", "width": 320,
                                    "height": 180, "hardware": False, "quality": 30}}
            baseline, _ = render_engine.render_project("baseline", base_spec, root, root, lambda *_: None)
            edited_spec = copy.deepcopy(base_spec)
            edited_spec["clips"][0].update({
                "mute": True, "brightness": .22, "contrast": 1.35, "saturation": .55,
                "gamma": 1.4, "temperature": 35, "tint": -18, "hue": 12,
                "shadows": 25, "highlights": -20, "zoom": 1.18,
                "rotation": 3, "mirrorH": True, "filter": "cinematic", "filterIntensity": .75,
            })
            edited, _ = render_engine.render_project("edited", edited_spec, root, root, lambda *_: None)
            loud_spec = copy.deepcopy(base_spec)
            loud_spec["clips"][0].update({"volume": 2, "keyframes": {"volumeEnd": 3}})
            loud, _ = render_engine.render_project("loud", loud_spec, root, root, lambda *_: None)
            self.assertNotEqual(self.decoded_frame_digest(baseline), self.decoded_frame_digest(edited))
            baseline_rms = self.decoded_audio_rms(baseline)
            self.assertGreater(baseline_rms, 100)
            self.assertLess(self.decoded_audio_rms(edited), 2)
            self.assertGreater(self.decoded_audio_rms(loud), baseline_rms * 1.5)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_detached_a1_audio_replaces_muted_video_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, replacement = root / "source.mp4", root / "music.wav"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=c=navy:s=160x90:r=20:d=0.8", "-f", "lavfi", "-i",
                "sine=frequency=330:sample_rate=48000:duration=0.8", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], check=True)
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "sine=frequency=990:sample_rate=48000:duration=0.25", str(replacement),
            ], check=True)
            base_spec = {
                "ratio": "16:9", "fps": 20,
                "clips": [{"id": "video-1", "file": source.name, "track": 0, "start": 0,
                           "end": .7, "speed": 1, "mute": True,
                           "audioDetached": True,
                           "crop": {"x": 0, "y": 0, "w": 1, "h": 1}}],
                "export": {"container": "mp4", "codec": "h264", "width": 320,
                           "height": 180, "hardware": False, "quality": 30},
            }
            silent, _ = render_engine.render_project("detached-silent", base_spec, root, root, lambda *_: None)
            replaced_spec = copy.deepcopy(base_spec)
            replaced_spec["audioClips"] = [{
                "id": "audio-1", "file": replacement.name, "name": "Music", "start": .1,
                "duration": .5, "sourceStart": 0, "speed": 1, "volume": .8,
                "linkedClipId": "video-1",
            }]
            replaced, _ = render_engine.render_project("detached-replaced", replaced_spec, root, root, lambda *_: None)
            self.assertLess(self.decoded_audio_rms(silent), 2)
            self.assertGreater(self.decoded_audio_rms(replaced), 100)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_timed_sticker_is_composited_into_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, sticker = root / "source.mp4", root / "sticker.png"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=c=navy:s=160x90:r=20:d=0.8", "-f", "lavfi", "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], check=True)
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=c=yellow:s=48x32", "-frames:v", "1", str(sticker),
            ], check=True)
            base_spec = {
                "ratio": "16:9", "fps": 20,
                "clips": [{"file": source.name, "track": 0, "start": 0, "end": .7,
                           "speed": 1, "crop": {"x": 0, "y": 0, "w": 1, "h": 1}}],
                "export": {"container": "mp4", "codec": "h264", "width": 320,
                           "height": 180, "hardware": False, "quality": 30},
            }
            baseline, _ = render_engine.render_project("sticker-baseline", base_spec, root, root, lambda *_: None)
            sticker_spec = copy.deepcopy(base_spec)
            sticker_spec["stickers"] = [{
                "file": sticker.name, "name": "Test sticker", "start": .1, "duration": .35,
                "x": .5, "y": .5, "scale": .3, "rotation": 12, "opacity": .8,
            }]
            rendered, details = render_engine.render_project("sticker-rendered", sticker_spec, root, root, lambda *_: None)
            self.assertTrue(rendered.is_file())
            self.assertEqual([], details["warnings"])
            self.assertNotEqual(self.decoded_frame_digest(baseline, .2),
                                self.decoded_frame_digest(rendered, .2))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_depth_separated_photo_motion_is_animated_in_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photo, depth = root / "photo.png", root / "depth.png"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "testsrc2=size=320x180", "-frames:v", "1", str(photo),
            ], check=True)
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=c=black:size=320x180", "-vf", "drawbox=x=90:y=25:w=140:h=145:color=white:t=fill",
                "-frames:v", "1", str(depth),
            ], check=True)
            spec = {
                "ratio": "16:9", "fps": 20,
                "clips": [{
                    "file": photo.name, "kind": "freeze", "track": 0, "duration": .7,
                    "crop": {"x": 0, "y": 0, "w": 1, "h": 1},
                    "photoMotion": {"enabled": True, "preset": "orbit-right",
                                    "depthMap": depth.name, "depthStrength": .9,
                                    "travel": .1, "focusX": .5, "focusY": .45,
                                    "edgeFill": 1.08, "easing": "ease-in-out"},
                }],
                "export": {"container": "mp4", "codec": "h264", "width": 320,
                           "height": 180, "hardware": False, "quality": 30},
            }
            output, details = render_engine.render_project("photo-motion", spec, root, root, lambda *_: None)
            self.assertTrue(output.is_file())
            self.assertEqual([], details["warnings"])
            self.assertNotEqual(self.decoded_frame_digest(output, .08),
                                self.decoded_frame_digest(output, .58))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_transitions_overlays_titles_music_and_voiceover_render_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first.mp4", root / "second.mp4"
            overlay, voice = root / "overlay.png", root / "voice.wav"
            for path, color, tone in ((first, "red", 330), (second, "blue", 550)):
                subprocess.run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"color=c={color}:s=160x90:r=20:d=0.55", "-f", "lavfi", "-i",
                    f"sine=frequency={tone}:sample_rate=48000:duration=0.55", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
                ], check=True)
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=yellow:s=40x30", "-frames:v", "1", str(overlay)], check=True)
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "sine=frequency=880:sample_rate=48000:duration=0.3", str(voice)], check=True)
            clips = [
                {"file": first.name, "track": 0, "start": 0, "end": .5, "speed": 1},
                {"file": second.name, "track": 0, "start": 0, "end": .5, "speed": 1,
                 "transition": "dissolve", "transitionDuration": .15},
                {"file": overlay.name, "kind": "freeze", "track": 1, "timelineStart": .15,
                 "duration": .35, "scale": .3, "positionX": .8, "positionY": .2, "opacity": .8},
            ]
            spec = {
                "name": "Integration", "ratio": "16:9", "fps": 20, "clips": clips,
                "title": "Opening", "watermark": "VDODesk", "audio": voice.name,
                "musicVolume": .15, "voiceovers": [{"file": voice.name, "start": .2, "volume": .8}],
                "audioDucking": True,
                "imageWatermark": {"file": overlay.name, "scale": .12, "opacity": .7, "x": .8, "y": .08},
                "export": {"container": "mp4", "codec": "h264", "width": 320,
                           "height": 180, "hardware": False, "quality": 32},
            }
            output, details = render_engine.render_project("integrated", spec, root, root, lambda *_: None)
            self.assertTrue(output.is_file())
            self.assertEqual("libx264", details["codec"])
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                "-of", "json", str(output),
            ], check=True, capture_output=True, text=True).stdout
            self.assertIn('"codec_type": "video"', probe)
            self.assertIn('"codec_type": "audio"', probe)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_title_export_falls_back_to_libass_without_drawtext(self):
        available = render_engine.filter_capabilities()
        if not (available.get("ass") or available.get("subtitles")):
            self.skipTest("libass text filter is required")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=c=navy:s=160x90:r=20:d=0.5", "-f", "lavfi", "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000", "-shortest", "-t", "0.5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], check=True)
            spec = {
                "ratio": "16:9", "fps": 20,
                "clips": [{"file": source.name, "track": 0, "start": 0, "end": .45, "speed": 1,
                           "anchorText": "Tracked label",
                           "tracking": {"focus": {"x": .5, "y": .4},
                                        "path": [{"x": .35, "y": .4}, {"x": .65, "y": .4}]}}],
                "title": "Opening title", "watermark": "VDODesk",
                "export": {"container": "mp4", "codec": "h264", "width": 320,
                           "height": 180, "hardware": False, "quality": 32},
            }
            fallback = {"drawtext": False, "ass": available.get("ass", False),
                        "subtitles": available.get("subtitles", False)}
            with mock.patch.object(render_engine, "filter_capabilities", return_value=fallback):
                output, details = render_engine.render_project(
                    "ass-fallback", spec, root, root, lambda *_: None)
            without_text = copy.deepcopy(spec)
            without_text["title"] = ""
            without_text["watermark"] = ""
            without_text["clips"][0]["anchorText"] = ""
            with mock.patch.object(render_engine, "filter_capabilities", return_value={}):
                baseline, _ = render_engine.render_project(
                    "no-text", without_text, root, root, lambda *_: None)
            native_renderer = render_engine.render_text_png
            def force_dependency_free_renderer(*args, **kwargs):
                kwargs["prefer_pillow"] = False
                return native_renderer(*args, **kwargs)
            builtin_project_spec = copy.deepcopy(spec)
            builtin_project_spec["clips"][0]["anchorText"] = ""
            builtin_anchor_spec = copy.deepcopy(spec)
            builtin_anchor_spec["title"] = ""
            builtin_anchor_spec["watermark"] = ""
            with mock.patch.object(render_engine, "filter_capabilities", return_value={}), \
                    mock.patch.object(render_engine, "render_text_png", side_effect=force_dependency_free_renderer):
                builtin, builtin_details = render_engine.render_project(
                    "builtin-project-text", builtin_project_spec, root, root, lambda *_: None)
                builtin_anchor, _ = render_engine.render_project(
                    "builtin-anchor-text", builtin_anchor_spec, root, root, lambda *_: None)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1000)
            self.assertNotEqual(self.decoded_frame_digest(output, .2),
                                self.decoded_frame_digest(baseline, .2))
            self.assertNotEqual(self.decoded_frame_digest(builtin, .2),
                                self.decoded_frame_digest(baseline, .2))
            self.assertNotEqual(self.decoded_frame_digest(builtin_anchor, .2),
                                self.decoded_frame_digest(baseline, .2))
            self.assertEqual("libass", details["textRenderer"])
            self.assertEqual([], details["warnings"])
            self.assertEqual("builtin-image", builtin_details["textRenderer"])
            self.assertEqual([], builtin_details["warnings"])


if __name__ == "__main__":
    unittest.main()
