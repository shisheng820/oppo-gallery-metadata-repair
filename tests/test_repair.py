import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class RepairIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "input.jpg"
        Image.new("RGB", (32, 32), "gray").save(self.source)
        subprocess.run(["exiftool", "-overwrite_original", "-Artist=Preserve this tag",
                        "-LensMake=Google", "-LensModel=Pixel 4 XL back camera 4.38mm f/1.73",
                        str(self.source)], check=True, capture_output=True)
        self.original = self.source.read_bytes()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "repair.py"), str(self.source),
                               *map(str, args)], capture_output=True, text=True)

    def test_preview_never_writes(self):
        out = self.base / "output"
        result = self.run_tool("--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(out.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_apply_preserves_source_and_unrelated_tags(self):
        out = self.base / "output"
        result = self.run_tool("--output", out, "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.source.read_bytes(), self.original)
        photo = next(out.glob("*.jpg"))
        tags = json.loads(subprocess.check_output(["exiftool", "-j", str(photo)]))[0]
        self.assertEqual(tags["Make"], "Google")
        self.assertEqual(tags["Model"], "Pixel 4 XL")
        self.assertEqual(tags["Artist"], "Preserve this tag")
        with Image.open(self.source) as a, Image.open(photo) as b:
            self.assertEqual(a.tobytes(), b.tobytes())
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        self.assertTrue(report["source_unchanged"])
        self.assertTrue(report["jpeg_scan_unchanged"])
        self.assertNotEqual(self.run_tool("--output", out, "--apply").returncode, 0)

    def test_no_model_guess_from_filename(self):
        subprocess.run(["exiftool", "-overwrite_original", "-LensModel=", str(self.source)],
                       check=True, capture_output=True)
        self.assertNotEqual(self.run_tool("--output", self.base / "out").returncode, 0)

    def test_output_cannot_be_source_directory(self):
        self.assertNotEqual(self.run_tool("--output", self.base, "--apply").returncode, 0)


if __name__ == "__main__":
    unittest.main()
