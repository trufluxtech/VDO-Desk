import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
import media_services


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class MediaServicesTests(unittest.TestCase):
    def test_local_photo_depth_map_is_generated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, depth = root / "photo.png", root / "depth.png"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "testsrc2=size=240x160", "-frames:v", "1", str(source),
            ], check=True)
            details = media_services.create_photo_depth_map(source, depth, .55, .42, .34)
            self.assertTrue(depth.is_file())
            self.assertGreater(depth.stat().st_size, 100)
            self.assertIn("engine", details)
            info = media_services.probe_media(depth)
            self.assertEqual((240, 160), (info["width"], info["height"]))

    def test_waveform_freeze_proxy_and_manual_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, freeze, proxy, mask = (root / "source.mp4", root / "freeze.jpg",
                                            root / "proxy.mp4", root / "mask.png")
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "testsrc2=size=160x90:rate=15:duration=0.6", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=48000:duration=0.6", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
            ], check=True)
            info = media_services.probe_media(source)
            self.assertEqual("video", info["kind"])
            self.assertTrue(info["hasAudio"])
            self.assertEqual("h264", info["videoCodec"])
            self.assertTrue(info["browserPlayable"])
            peaks = media_services.audio_waveform(source, 64)
            self.assertEqual(64, len(peaks))
            self.assertGreater(max(peaks), .01)
            media_services.extract_freeze(source, freeze, .2)
            self.assertGreater(freeze.stat().st_size, 100)
            media_services.create_proxy(source, proxy, hardware=False)
            self.assertTrue(proxy.is_file())
            result = media_services.analyze_subject(
                source, .1, {"x": .1, "y": .1, "w": .5, "h": .7}, mask, .5)
            self.assertIn("box", result)
            self.assertIn("focus", result)
            self.assertTrue(0 <= result["focus"]["x"] <= 1)


if __name__ == "__main__":
    unittest.main()
