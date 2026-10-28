import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Video lab requires FFmpeg/ffprobe')
class VideoLabIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
            'testsrc2=size=64x64:rate=10', '-f', 'lavfi', '-i', 'sine=frequency=440',
            '-t', '0.3', '-c:v', 'libx264', '-c:a', 'aac', str(self.source)],
            check=True, capture_output=True)
        self.original = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def run_lab(self, output, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/video_lab.py'),
            str(self.source), '--output', str(output), *args], capture_output=True)

    def test_preview_never_creates_output(self):
        output = self.base / 'preview'
        result = self.run_lab(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['preview'])
        self.assertFalse(output.exists())

    def test_copies_preserve_packets_and_read_back_custom_fields(self):
        output = self.base / 'copies'
        result = self.run_lab(output, '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((output / 'report.json').read_text())
        self.assertTrue(report['source_unchanged'])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original)
        self.assertEqual(len(report['samples']), 5)
        self.assertTrue(all(s['packet_payload_and_timing_unchanged'] for s in report['samples']))
        tags = json.loads(subprocess.check_output(['exiftool', '-j', '-G1', '-s', '-n',
            str(output / 'CUSTOM_VIDEO.mp4')], stderr=subprocess.DEVNULL))[0]
        for field in ('Keys:Model', 'Keys:AndroidModel', 'Keys:OplusProductModel'):
            self.assertEqual(tags[field], 'Custom Video Camera')
        self.assertEqual(tags['QuickTime:CreateDate'], '2020:06:01 04:34:56')
        self.assertAlmostEqual(float(tags['Composite:GPSLatitude']), 39.9087, places=5)
        self.assertAlmostEqual(float(tags['Composite:GPSLongitude']), 116.3975, places=5)
        self.assertNotEqual(self.run_lab(output, '--apply').returncode, 0)


if __name__ == '__main__':
    unittest.main()
