import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class BatchRepairIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.input = self.base / "input"
        self.input.mkdir()
        self.source = self.input / "IMG_20200601_123456.jpg"
        Image.new("RGB", (32, 32), "gray").save(self.source)
        subprocess.run(["exiftool", "-overwrite_original", "-Artist=Preserve this tag",
                        "-LensMake=Google", "-LensModel=Pixel 4 XL back camera 4.38mm f/1.73",
                        str(self.source)], check=True, capture_output=True)
        self.original = self.source.read_bytes()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "repair.py"), str(self.input),
                               *map(str, args)], capture_output=True, text=True, encoding="utf-8")

    def test_preview_never_writes(self):
        out = self.base / "output"
        result = self.run_tool("--output", out, "--model", "My Camera")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(out.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_apply_preserves_source_and_unrelated_tags(self):
        out = self.base / "output"
        result = self.run_tool("--output", out, "--make", "Google", "--model", "Pixel 4 XL", "--apply")
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
        self.assertTrue(report["files"][0]["source_unchanged"])
        self.assertTrue(report["files"][0]["jpeg_scan_unchanged"])
        self.assertNotEqual(self.run_tool("--output", out, "--apply").returncode, 0)

    def test_no_implicit_changes(self):
        subprocess.run(["exiftool", "-overwrite_original", "-LensModel=", str(self.source)],
                       check=True, capture_output=True)
        self.assertNotEqual(self.run_tool("--output", self.base / "out").returncode, 0)

    def test_output_cannot_be_source_directory(self):
        self.assertNotEqual(self.run_tool("--output", self.input / "out", "--model", "Demo", "--apply").returncode, 0)

    def test_recursive_preserves_relative_paths(self):
        nested = self.input / "sub"
        nested.mkdir()
        (nested / self.source.name).write_bytes(self.original)
        (self.input / "notes.txt").write_text("Do not process", encoding="utf-8")
        out = self.base / "output"
        result = self.run_tool("--output", out, "--model", "Any Camera", "--recursive", "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((out / "sub" / self.source.name).exists())
        self.assertFalse((out / "notes.txt").exists())
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["updated"], 2)
        self.assertEqual(report["summary"]["unsupported"], 1)

    def test_full_profile_round_trip(self):
        profile = self.base / "profile.json"
        profile.write_text(json.dumps({"make": "Demo", "model": "ColorOS EXIF Demo",
            "taken_at": "2020:06:01 12:34:56", "utc_offset": "+08:00",
            "latitude": -33.8568, "longitude": 151.2153, "altitude": -12,
            "iso": 200, "aperture": 2.8, "exposure": "1/125", "ev": -0.7,
            "focal_length": 35, "focal_length_35mm": 50}), encoding="utf-8")
        out = self.base / "output"
        result = self.run_tool("--output", out, "--profile", profile, "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(subprocess.check_output(["exiftool", "-j", "-G1", "-n", str(out / self.source.name)],
                                                  stderr=subprocess.DEVNULL))[0]
        self.assertEqual(data["IFD0:Model"], "ColorOS EXIF Demo")
        self.assertEqual(data["ExifIFD:DateTimeOriginal"], "2020:06:01 12:34:56")
        self.assertEqual(data["ExifIFD:OffsetTimeOriginal"], "+08:00")
        self.assertEqual(data["GPS:GPSLatitudeRef"], "S")
        self.assertAlmostEqual(data["GPS:GPSLatitude"], 33.8568, places=5)
        self.assertEqual(data["GPS:GPSLongitudeRef"], "E")
        self.assertEqual(data["GPS:GPSAltitudeRef"], 1)
        self.assertEqual(data["ExifIFD:ISO"], 200)
        self.assertAlmostEqual(data["ExifIFD:FNumber"], 2.8, places=3)
        self.assertAlmostEqual(data["ExifIFD:ExposureTime"], 1/125, places=6)
        self.assertAlmostEqual(data["ExifIFD:ExposureCompensation"], -0.7, places=3)
        self.assertEqual(data["ExifIFD:FocalLengthIn35mmFormat"], 50)

    def test_filename_time_does_not_guess_unknown_names(self):
        (self.input / "IMG_1234.jpg").write_bytes(self.original)
        out = self.base / "output"
        result = self.run_tool("--output", out, "--from-filename-time", "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(subprocess.check_output(["exiftool", "-j", str(out / self.source.name)],
                                                  stderr=subprocess.DEVNULL))[0]
        self.assertEqual(data["DateTimeOriginal"], "2020:06:01 12:34:56")
        self.assertFalse((out / "IMG_1234.jpg").exists())
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["skipped"], 1)

    def test_only_missing_keeps_existing_model(self):
        subprocess.run(["exiftool", "-overwrite_original", "-Model=Old Camera", str(self.source)],
                       check=True, capture_output=True)
        out = self.base / "output"
        result = self.run_tool("--output", out, "--model", "New Camera", "--make", "Demo", "--only-missing", "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(subprocess.check_output(["exiftool", "-j", str(out / self.source.name)],
                                                  stderr=subprocess.DEVNULL))[0]
        self.assertEqual(data["Model"], "Old Camera")
        self.assertEqual(data["Make"], "Demo")

    def test_invalid_values_fail_before_writing(self):
        out = self.base / "output"
        for options in (("--latitude", "99", "--longitude", "0"),
                        ("--latitude", "12"), ("--exposure", "0"),
                        ("--taken-at", "2020:02:30 12:00:00"),
                        ("--utc-offset", "+25:00", "--model", "Demo")):
            with self.subTest(options=options):
                result = self.run_tool("--output", out, *options, "--apply")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(out.exists())
                self.assertEqual(self.original, self.source.read_bytes())

    def test_profile_typos_are_refused(self):
        profile = self.base / "bad.json"
        profile.write_text('{"modle": "Typo"}', encoding="utf-8")
        out = self.base / "output"
        result = self.run_tool("--output", out, "--profile", profile, "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("modle", result.stderr)
        self.assertFalse(out.exists())

    def test_unicode_filename_and_millisecond_time(self):
        (self.input / "假期 空格.JPG").write_bytes(self.original)
        out = self.base / "output"
        result = self.run_tool("--output", out, "--taken-at", "2020:06:01 12:34:56.007",
                               "--utc-offset=-03:00", "--apply")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        data = json.loads(subprocess.check_output(["exiftool", "-j", "-SubSecTimeOriginal",
            "-OffsetTimeOriginal", str(out / self.source.name)], stderr=subprocess.DEVNULL))[0]
        self.assertEqual(str(data["SubSecTimeOriginal"]), "007")
        self.assertEqual(data["OffsetTimeOriginal"], "-03:00")
        self.assertTrue((out / "假期 空格.JPG").exists())


if __name__ == "__main__":
    unittest.main()
