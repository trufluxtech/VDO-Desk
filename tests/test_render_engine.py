from array import array
import copy
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
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

    def test_all_clip_filter_presets_build_ffmpeg_chains(self):
        presets = {"cinematic", "warm", "cool", "vintage", "mono", "noir", "vivid", "soft", "teal_orange"}
        for preset in presets:
            with self.subTest(preset=preset):
                self.assertTrue(render_engine.clip_filter_chain({"filter": preset, "filterIntensity": .65}))
        self.assertEqual([], render_engine.clip_filter_chain({"filter": "none", "filterIntensity": 1}))
        self.assertEqual([], render_engine.clip_filter_chain({"filter": "vivid", "filterIntensity": 0}))
        self.assertEqual([], render_engine.clip_filter_chain({"filter": "untrusted", "filterIntensity": 1}))

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


if __name__ == "__main__":
    unittest.main()
