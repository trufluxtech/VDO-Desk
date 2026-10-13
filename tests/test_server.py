import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "app" / "server.py"
sys.path.insert(0, str(SERVER_PATH.parent))
SPEC = importlib.util.spec_from_file_location("vdodesk_server", SERVER_PATH)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class RecentFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old_media = server.MEDIA
        self.old_recent = server.RECENT_PATH
        server.MEDIA = root / "media"
        server.MEDIA.mkdir()
        server.RECENT_PATH = root / "recent-files.json"

    def tearDown(self):
        server.MEDIA = self.old_media
        server.RECENT_PATH = self.old_recent
        self.temp.cleanup()

    def test_remembers_only_latest_ten_existing_files(self):
        for index in range(12):
            path = server.MEDIA / f"{index:02d}-still.png"
            path.write_bytes(b"media")
            server.remember_file(path, f"Clip {index}", index + 1)

        items = server.recent_files()
        self.assertEqual(10, len(items))
        self.assertEqual("Clip 11", items[0]["name"])
        self.assertEqual("Clip 2", items[-1]["name"])

    def test_missing_files_are_removed(self):
        path = server.MEDIA / "present.png"
        path.write_bytes(b"media")
        server.remember_file(path, "Present", 3.5)
        server.RECENT_PATH.write_text(
            '[{"file":"missing.png","name":"Missing","duration":1},'
            '{"file":"present.png","name":"Present","duration":3.5}]',
            encoding="utf-8",
        )

        items = server.recent_files()
        self.assertEqual(["present.png"], [item["file"] for item in items])

    def test_all_media_exposes_assets_outside_recent_ten(self):
        for index in range(12):
            path = server.MEDIA / f"{index:02d}-still.png"
            path.write_bytes(b"media")
        items = server.all_media_files()
        self.assertEqual(12, len(items))
        self.assertEqual({path.name for path in server.MEDIA.iterdir()},
                         {item["file"] for item in items})

    def test_filename_cleaning_and_safe_name_block_path_traversal(self):
        self.assertEqual("passwd", server.clean_filename("../../passwd"))
        self.assertEqual("evil_.mp4", server.clean_filename("evil?.mp4"))
        self.assertEqual("clip.mp4", server.safe_name("../../clip.mp4"))


if __name__ == "__main__":
    unittest.main()
