"""Copy-only JPEG camera metadata repair. No device access in preview mode."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_hash(data: bytes) -> str:
    """Hash from first Start Of Scan onward, skipping length-delimited headers."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("Only JPEG files are supported")
    pos = 2
    while pos < len(data):
        if data[pos] != 255:
            raise ValueError("Invalid JPEG marker")
        while pos < len(data) and data[pos] == 255:
            pos += 1
        marker = data[pos]
        pos += 1
        if marker == 0xDA:
            return sha256(data[pos - 2:])
        if marker == 0xD9:
            break
        if marker in (0x01, *range(0xD0, 0xD9)):
            continue
        size = int.from_bytes(data[pos:pos + 2], "big")
        if size < 2:
            break
        pos += size
    raise ValueError("JPEG scan not found")


def exif(tool: str, *args: str):
    result = subprocess.run([tool, *args], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result


def tags(tool: str, path: Path) -> dict:
    return json.loads(exif(tool, "-j", "-G1", "-a", "-s", "-n", str(path)).stdout)[0]


def repair(source: Path, output: Path, tool: str, make: str | None,
           model: str | None, apply: bool) -> dict:
    source, output = source.resolve(strict=True), output.resolve()
    if not source.is_file() or source.suffix.lower() not in (".jpg", ".jpeg"):
        raise ValueError("Input must be a JPEG file")
    if output == source.parent or output in source.parents:
        raise ValueError("Output must be a separate new directory")
    if output.exists():
        raise ValueError("Output already exists; choose a new directory (no overwrite)")
    before = tags(tool, source)
    lens = str(before.get("ExifIFD:LensModel", "")).strip("\x00 ")
    lens_match = re.fullmatch(r"(.+?) (?:back|front) camera .+", lens)
    make = make or str(before.get("ExifIFD:LensMake", "")).strip("\x00 ")
    model = model or (lens_match.group(1) if lens_match else None)
    if not make or not model or any(ord(c) < 32 for c in make + model):
        raise ValueError("Cannot infer camera identity; supply --make and --model from trusted evidence")
    original = source.read_bytes()
    image_hash = scan_hash(original)
    plan = {"make": make, "model": model, "mode": "apply" if apply else "preview",
            "evidence": {"lens_make": before.get("ExifIFD:LensMake"), "lens_model": lens},
            "changes": {"IFD0:Make": [before.get("IFD0:Make"), make],
                        "IFD0:Model": [before.get("IFD0:Model"), model]}}
    if not apply:
        return plan
    output.mkdir(parents=True, exist_ok=False)
    target = output / "repaired.jpg"
    shutil.copy2(source, target)
    write = exif(tool, "-P", f"-IFD0:Make={make}", f"-IFD0:Model={model}", str(target))
    after = tags(tool, target)
    plan.update({"source_sha256": sha256(original), "output_sha256": sha256(target.read_bytes()),
                 "source_unchanged": sha256(source.read_bytes()) == sha256(original),
                 "jpeg_scan_unchanged": scan_hash(target.read_bytes()) == image_hash,
                 "metadata_matches": after.get("IFD0:Make") == make and after.get("IFD0:Model") == model,
                 "exiftool_warnings": write.stderr.decode("utf-8", errors="replace").strip()})
    for name, data in (("before.json", before), ("after.json", after), ("report.json", plan)):
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if not all(plan[k] for k in ("source_unchanged", "jpeg_scan_unchanged", "metadata_matches")):
        raise RuntimeError("Verification failed; inspect local reports, do not sync")
    return plan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--output", type=Path, required=True, help="New private directory; never reused")
    p.add_argument("--exiftool", default="exiftool")
    p.add_argument("--make")
    p.add_argument("--model")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    try:
        print(json.dumps(repair(a.source, a.output, a.exiftool, a.make, a.model, a.apply),
                         ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
