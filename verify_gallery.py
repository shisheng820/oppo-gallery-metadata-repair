"""Transfer one repaired copy with ADB; scan/open/assert with FIRERPA on main display."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid

from lamda.client import Device

PACKAGE = "com.coloros.gallery3d"
PREFIX = PACKAGE + ":id/"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("photo", type=Path)
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=65000)
    p.add_argument("--certificate")
    p.add_argument("--serial", required=True, help="ADB serial from adb devices")
    p.add_argument("--expected-model", required=True)
    p.add_argument("--evidence", type=Path, required=True, help="New private output directory")
    a = p.parse_args()
    photo = a.photo.resolve(strict=True)
    if a.evidence.exists():
        raise ValueError("Evidence directory already exists")
    a.evidence.mkdir(parents=True)
    d = Device(a.host, port=a.port, certificate=a.certificate)
    d.set_debug_log_enabled(True)
    d.server_info()

    def shell(command):
        r = d.execute_script(command, timeout=30)
        if r.exitstatus:
            raise RuntimeError(r.stderr.decode("utf-8", errors="replace"))
        return r.stdout.decode("utf-8", errors="replace")

    # pm handles system apps too; the skill CLI app-check excludes system apps.
    if not shell("pm path " + PACKAGE).startswith("package:"):
        raise RuntimeError("System gallery is missing")
    # Ensure FireRPA and ADB point at the SAME device before transferring anything.
    def adb(*args):
        return subprocess.check_output(["adb", "-s", a.serial, *args], stderr=subprocess.STDOUT)

    nonce = "metadata-repair-" + uuid.uuid4().hex
    proof = "/data/local/tmp/" + nonce
    shell("printf %s " + shlex.quote(nonce) + " > " + shlex.quote(proof)
          + " && chmod 644 " + shlex.quote(proof))
    try:
        if adb("shell", "cat", proof).decode().strip() != nonce:
            raise RuntimeError("ADB and FireRPA are different devices")
    finally:
        shell("rm -f " + shlex.quote(proof))
    folder = "/sdcard/Pictures/MetadataRepair-" + uuid.uuid4().hex[:12]
    remote = folder + "/repaired.jpg"
    shell("mkdir " + shlex.quote(folder))
    adb("push", str(photo), remote)
    expected_hash = hashlib.sha256(photo.read_bytes()).hexdigest()
    if shell("sha256sum " + shlex.quote(remote)).split()[0] != expected_hash:
        raise RuntimeError("Transferred file hash mismatch")
    shell("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d " + shlex.quote("file://" + remote))
    media_id = None
    for _ in range(10):
        rows = shell("content query --uri content://media/external/images/media --projection _id:_data")
        for row in rows.splitlines():
            if row.rstrip().endswith(folder.replace("/sdcard/", "/storage/emulated/0/") + "/repaired.jpg"):
                match = re.search(r"_id=(\d+)", row)
                if match:
                    media_id = match.group(1)
        if media_id:
            break
        time.sleep(0.5)  # Supplemental delay; the next query checks actual scan state.
    if not media_id:
        raise RuntimeError("MediaStore did not index the test copy; original files were untouched")
    shell("am force-stop " + PACKAGE)
    shell("am start -W -a android.intent.action.VIEW -d content://media/external/images/media/"
          + media_id + " -t image/jpeg -p " + PACKAGE)
    details = d(resourceId=PREFIX + "action_details")
    if not details.wait_for_exists(10000):
        raise RuntimeError("Details button unavailable; inspect UI with the FIRERPA CLI")
    if d.current_application().info().packageName != PACKAGE:
        raise RuntimeError("Gallery did not open (possible user-control dialog)")
    d.wait_for_idle(1000)
    details.click()
    model = d(resourceId=PREFIX + "tv_model")
    if not model.wait_for_exists(3000):
        # On this gallery a button may exist during the opening animation, yet
        # its first click is ignored. Retry ONCE, only if still on the photo UI.
        if d.current_application().info().packageName != PACKAGE or not details.exists():
            raise RuntimeError("Gallery left the expected photo screen")
        d.wait_for_idle(1000)
        d(resourceId=PREFIX + "action_details").click()
        if not model.wait_for_exists(5000):
            raise RuntimeError("Gallery model row unavailable after one retry")
    observed = model.get_text()
    # Check filename/path as well, so another photo's model cannot satisfy the test.
    filename = d(resourceId=PREFIX + "tv_full_name").get_text()
    path = d(resourceId=PREFIX + "tv_path").get_text()
    verified = (observed == a.expected_model and filename.lower() == "repaired.jpg"
                and folder.split("/")[-1] in path and d.current_application().info().packageName == PACKAGE)
    report = {"verified": verified, "expected_model": a.expected_model, "observed_model": observed,
              "transfer_sha256_matches": True, "remote_copy": remote, "media_id": media_id}
    (a.evidence / "device-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not verified:
        raise RuntimeError("Visible result did not match the test photo and expected model")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
