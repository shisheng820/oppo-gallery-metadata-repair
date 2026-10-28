"""Batch-edit JPEG EXIF into a new folder. Default: read-only preview."""
from __future__ import annotations

import argparse
from datetime import datetime
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

from oplus_metadata import inspect_bytes

FIELDS = ("make", "model", "taken_at", "utc_offset", "latitude", "longitude",
          "altitude", "iso", "aperture", "exposure", "ev", "focal_length",
          "focal_length_35mm", "lens_make", "lens_model")
SUPPORTED = {".jpg", ".jpeg"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def scan_hash(data):
    """Hash from the first SOS marker onward: never decode/re-encode the image."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("Not a JPEG")
    pos = 2
    while pos < len(data):
        if data[pos] != 255:
            break
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker == 0xDA:
            return sha256(data[pos - 2:])
        if marker == 0xD9:
            break
        if marker in (0x01, *range(0xD0, 0xD9)):
            continue
        if pos + 2 > len(data):
            break
        size = int.from_bytes(data[pos:pos + 2], "big")
        if size < 2:
            break
        pos += size
    raise ValueError("JPEG scan not found")


def exif(tool, *args):
    # A UTF-8 argument file over stdin also survives Windows launcher/code-page
    # conversions. Quoting is unnecessary: each line is one complete argument.
    if any("\n" in arg or "\r" in arg for arg in args):
        raise ValueError("Newlines are not supported in paths or field values")
    result = subprocess.run([tool, "-charset", "filename=UTF8", "-@", "-"],
                            input=("\n".join(args) + "\n").encode("utf-8"),
                            capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result


def read_tags(tool, photo):
    return json.loads(exif(tool, "-j", "-G1", "-a", "-s", "-n", str(photo)).stdout)[0]


def number(value, label, low=None, high=None, positive=False):
    if isinstance(value, bool):
        raise ValueError(f"{label}: boolean is not a number")
    try:
        value = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        raise ValueError(f"{label}: invalid number") from None
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{label}: must be finite and positive")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(f"{label}: out of range")
    return value


def time_changes(value):
    match = re.fullmatch(r"(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?", str(value))
    if not match:
        raise ValueError("taken_at: use YYYY:MM:DD HH:MM:SS[.sss]")
    stamp = ":".join(match.group(i) for i in (1, 2, 3)) + " " + match.group(4)
    datetime.strptime(stamp, "%Y:%m:%d %H:%M:%S")
    fraction = match.group(5) or ""
    return {"ExifIFD:DateTimeOriginal": stamp, "ExifIFD:CreateDate": stamp,
            "IFD0:ModifyDate": stamp, "ExifIFD:SubSecTimeOriginal": fraction,
            "ExifIFD:SubSecTimeDigitized": fraction, "ExifIFD:SubSecTime": fraction}


def build_changes(config):
    changes = {}
    for key, tag in (("make", "IFD0:Make"), ("model", "IFD0:Model"),
                     ("lens_make", "ExifIFD:LensMake"), ("lens_model", "ExifIFD:LensModel")):
        if key in config:
            value = config[key]
            if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                raise ValueError(f"{key}: nonempty text required")
            changes[tag] = value
    if "taken_at" in config:
        changes.update(time_changes(config["taken_at"]))
    if "utc_offset" in config:
        offset = str(config["utc_offset"])
        if not re.fullmatch(r"[+-](?:0\d|1[0-4]):[0-5]\d", offset) or (offset[1:3] == "14" and offset[4:] != "00"):
            raise ValueError("utc_offset: use a valid offset such as +08:00")
        changes.update({f"ExifIFD:{tag}": offset for tag in ("OffsetTimeOriginal", "OffsetTimeDigitized", "OffsetTime")})
    if ("latitude" in config) != ("longitude" in config):
        raise ValueError("latitude and longitude must be supplied together")
    if "latitude" in config:
        lat = number(config["latitude"], "latitude", -90, 90)
        lon = number(config["longitude"], "longitude", -180, 180)
        changes.update({"GPS:GPSLatitude": abs(lat), "GPS:GPSLatitudeRef": "S" if lat < 0 else "N",
                        "GPS:GPSLongitude": abs(lon), "GPS:GPSLongitudeRef": "W" if lon < 0 else "E",
                        "GPS:GPSMapDatum": "WGS-84"})
    if "altitude" in config:
        height = number(config["altitude"], "altitude")
        changes.update({"GPS:GPSAltitude": abs(height), "GPS:GPSAltitudeRef": int(height < 0)})
    for key, tag in (("iso", "ISO"), ("aperture", "FNumber"), ("exposure", "ExposureTime"),
                     ("ev", "ExposureCompensation"), ("focal_length", "FocalLength"),
                     ("focal_length_35mm", "FocalLengthIn35mmFormat")):
        if key not in config:
            continue
        value = number(config[key], key, positive=(key != "ev"))
        if key in ("iso", "focal_length_35mm"):
            if not value.is_integer() or value > 65535:
                raise ValueError(f"{key}: use an integer between 1 and 65535")
            value = int(value)
        changes["ExifIFD:" + tag] = value
        # Keep APEX representations consistent with the primary photographic values.
        if key == "aperture":
            changes["ExifIFD:ApertureValue"] = 2 * math.log2(value)
        if key == "exposure":
            changes["ExifIFD:ShutterSpeedValue"] = -math.log2(value)
    return changes


def filename_time(name):
    match = re.fullmatch(r"(?:PXL|IMG)_(\d{8})_(\d{6})(\d{3})?(?:\.[A-Za-z0-9_-]+)*\.jpe?g", name, re.I)
    if not match:
        raise ValueError("filename does not contain a supported complete capture time")
    value = datetime.strptime(match[1] + match[2], "%Y%m%d%H%M%S").strftime("%Y:%m:%d %H:%M:%S")
    return time_changes(value + ("." + match[3] if match[3] else ""))


def matches(actual, expected):
    if expected == "":
        return actual is None or actual == ""
    if isinstance(expected, (float, int)):
        return isinstance(actual, (float, int)) and math.isclose(actual, expected, rel_tol=1e-5, abs_tol=1e-7)
    return str(actual) == str(expected)


def batch(source, output, config, tool="exiftool", recursive=False, apply=False,
          from_filename_time=False, only_missing=False):
    source, output = source.resolve(strict=True), output.resolve()
    if output.exists():
        raise ValueError("Output already exists; choose a NEW folder")
    input_root = source if source.is_dir() else source.parent
    if output == input_root or input_root in output.parents or output in input_root.parents:
        raise ValueError("Input and output folders must be separate, not nested")
    if from_filename_time and "taken_at" in config:
        raise ValueError("Choose taken_at OR from-filename-time")
    common = build_changes(config)
    if not common and not from_filename_time:
        raise ValueError("Specify at least one field; no fields are inferred automatically")
    candidates = sorted(source.rglob("*") if recursive else source.iterdir()) if source.is_dir() else [source]
    files, unsupported, symlinks = [], [], []
    for path in candidates:
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            symlinks.append(str(path.relative_to(input_root)))
        elif path.is_file():
            if path.suffix.lower() in SUPPORTED:
                files.append(path)
            else:
                unsupported.append(str(path.relative_to(input_root)))
    if not files:
        raise ValueError("No supported JPEG files found")
    report = {"mode": "apply" if apply else "preview", "files": [],
              "unsupported": unsupported, "symlinks_skipped": symlinks,
              "summary": {"updated": 0, "planned": 0, "unchanged": 0, "skipped": 0, "failed": 0, "unsupported": len(unsupported)}}
    if apply:
        output.mkdir(parents=True, exist_ok=False)
    for photo in files:
        entry = {"file": str(photo.relative_to(input_root))}
        try:
            original = photo.read_bytes()
            if inspect_bytes(original)["compound"]:
                entry.update(status="skipped", reason="compound JPEG container: use a container-aware workflow; hidden media was not rewritten")
                report["summary"]["skipped"] += 1
                report["files"].append(entry)
                continue
            desired = dict(common)
            if from_filename_time:
                try:
                    desired.update(filename_time(photo.name))
                except ValueError as exc:
                    entry.update(status="skipped", reason=str(exc))
                    report["summary"]["skipped"] += 1
                    report["files"].append(entry)
                    continue
            before = read_tags(tool, photo)
            if only_missing:
                desired = {key: value for key, value in desired.items()
                           if before.get(key) is None or str(before[key]).strip("\x00 ") == ""}
            entry["changes"] = {key: {"before": before.get(key), "after": value} for key, value in desired.items()}
            image_hash = scan_hash(original)
            if not apply:
                entry["status"] = "planned"
                report["summary"]["planned"] += 1
            else:
                target = output / photo.relative_to(input_root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(photo, target)
                warning = ""
                if desired:
                    args = [f"-{key}#={value}" for key, value in desired.items()]
                    result = exif(tool, "-P", *args, str(target))
                    warning = result.stderr.decode("utf-8", errors="replace").strip()
                after = read_tags(tool, target)
                entry.update(source_sha256=sha256(original), output_sha256=sha256(target.read_bytes()),
                             source_unchanged=sha256(photo.read_bytes()) == sha256(original),
                             jpeg_scan_unchanged=scan_hash(target.read_bytes()) == image_hash,
                             fields_match=all(matches(after.get(key), value) for key, value in desired.items()),
                             readback={key: after.get(key) for key in desired}, warnings=warning)
                if not all(entry[key] for key in ("source_unchanged", "jpeg_scan_unchanged", "fields_match")):
                    raise RuntimeError("Readback or integrity verification failed")
                entry["status"] = "updated" if desired else "unchanged"
                report["summary"][entry["status"]] += 1
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            entry.update(status="failed", error=str(exc))
            report["summary"]["failed"] += 1
        report["files"].append(entry)
    if apply:
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path, help="JPEG file or folder")
    p.add_argument("--output", type=Path, required=True, help="New, separate output folder")
    p.add_argument("--profile", type=Path, help="JSON field values; command-line fields take precedence")
    p.add_argument("--exiftool", default="exiftool")
    for key in FIELDS:
        p.add_argument("--" + key.replace("_", "-"))
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--from-filename-time", action="store_true")
    p.add_argument("--only-missing", action="store_true")
    a = p.parse_args()
    try:
        config = json.loads(a.profile.read_text(encoding="utf-8-sig")) if a.profile else {}
        if not isinstance(config, dict):
            raise ValueError("Profile must be a JSON object")
        unknown = set(config) - set(FIELDS)
        if unknown:
            raise ValueError("Unknown profile fields: " + ", ".join(sorted(unknown)))
        config.update({key: getattr(a, key) for key in FIELDS if getattr(a, key) is not None})
        report = batch(a.source, a.output, config, a.exiftool, a.recursive, a.apply,
                       a.from_filename_time, a.only_missing)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["summary"]["failed"] else 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
