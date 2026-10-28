"""Audit Git-tracked publishable files. Does not read personal input folders."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    rb"(?:192\.168\.|10\.\d{1,3}\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}",
    rb"(?i)[A-Z]:[\\/]Users[\\/][^\s\"']+",
    rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-proj-[A-Za-z0-9_-]{15,}|ntn_[A-Za-z0-9]{15,})",
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
]


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    errors = []
    count = 0
    for rel in filter(None, paths):
        count += 1
        path = ROOT / rel
        if any(part in {".private", ".venv", "__pycache__"} for part in path.relative_to(ROOT).parts):
            errors.append(f"Private directory tracked: {rel}")
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            if rel not in {"docs/images/before-model.jpg", "docs/images/after-model.jpg"}:
                errors.append(f"Unapproved media: {rel}")
                continue
            tags = json.loads(subprocess.check_output(["exiftool", "-j", "-n", "-ImageWidth", "-ImageHeight",
                "-GPS:all", "-Artist", "-OwnerName", "-SerialNumber", "-UserComment", "-ImageDescription",
                "-Make", "-Model", str(path)], stderr=subprocess.DEVNULL))[0]
            allowed = {"SourceFile", "ImageWidth", "ImageHeight"}
            if set(tags) - allowed or tags.get("ImageWidth", 99999) > 1000 or tags.get("ImageHeight", 99999) > 160:
                errors.append(f"Image metadata or dimensions require review: {rel}")
        elif path.suffix.lower() in {".mp4", ".heic", ".png", ".log", ".xml", ".pem"}:
            errors.append(f"Unapproved artifact type: {rel}")
        else:
            content = path.read_bytes()
            if any(re.search(pattern, content) for pattern in PATTERNS):
                errors.append(f"Potential private information: {rel}")
    if not count:
        errors.append("No tracked files; stage the intended public files first")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Public-file audit passed: {count} tracked files. Manually review screenshots and the staged diff too.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
