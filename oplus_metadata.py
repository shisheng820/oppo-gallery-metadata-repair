"""Inspect observed OnePlus JPEG containers; build experimental, self-contained demos.

No donor-image import: previews, source images and videos must come from the new scene.
This is an observed format implementation, not an official Oplus specification.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET

XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\0"
NS = {"x": "adobe:ns:meta/", "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
      "GCamera": "http://ns.google.com/photos/1.0/camera/",
      "OpCamera": "http://ns.oplus.com/photos/1.0/camera/",
      "Container": "http://ns.google.com/photos/1.0/container/",
      "Item": "http://ns.google.com/photos/1.0/container/item/"}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def q(prefix, name):
    return "{" + NS[prefix] + "}" + name


def jpeg_end(data):
    """Locate the primary JPEG EOI by parsing markers, not by matching thumbnail bytes."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("Not a JPEG")
    pos = 2
    while pos < len(data):
        if data[pos] != 255:
            raise ValueError("Invalid JPEG marker")
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            return pos
        if marker in (0x01, *range(0xD0, 0xD9)):
            continue
        size = int.from_bytes(data[pos:pos + 2], "big")
        if size < 2 or pos + size > len(data):
            raise ValueError("Invalid JPEG segment length")
        pos += size
        if marker == 0xDA:
            while True:
                found = data.find(b"\xff", pos)
                if found < 0 or found + 1 >= len(data):
                    raise ValueError("Truncated JPEG scan")
                following = data[found + 1]
                if following == 0 or 0xD0 <= following <= 0xD7:
                    pos = found + 2
                    continue
                pos = found
                break
    raise ValueError("JPEG EOI not found")


def headers(data):
    pos = 2
    while pos + 4 <= len(data):
        start = pos
        if data[pos] != 255:
            raise ValueError("Invalid JPEG header")
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            raise ValueError("Truncated JPEG header")
        marker = data[pos]
        pos += 1
        if marker in (0xDA, 0xD9):
            return
        size = int.from_bytes(data[pos:pos + 2], "big")
        if size < 2 or pos + size > len(data):
            raise ValueError("Invalid JPEG header length")
        end = pos + size
        yield marker, start, end, data[pos + 2:end]
        pos = end


def parse_trailer(data):
    if len(data) < 8 or data[-8:-4] not in (b"jxrs", b"wtmk"):
        return None
    jlen = struct.unpack_from("<I", data, len(data) - 4)[0]
    if not 9 <= jlen <= min(len(data), 1_048_576):
        raise ValueError("Invalid trailer index length")
    anchor = len(data) - jlen
    index = json.loads(data[anchor:-8].rstrip(b"\0"))
    if not isinstance(index, list) or len(index) > 4096:
        raise ValueError("Invalid trailer directory")
    blocks, ranges = {}, []
    primary_end = jpeg_end(data)
    for entry in index:
        if not isinstance(entry, dict):
            raise ValueError("Invalid trailer entry")
        name, offset, length = entry.get("name"), entry.get("offset"), entry.get("length")
        if not isinstance(name, str) or name in blocks:
            raise ValueError("Duplicate or invalid block name")
        if type(offset) is not int or type(length) is not int or not 0 < length <= offset <= anchor:
            raise ValueError("Trailer block outside file")
        start = anchor - offset
        if start < primary_end:
            raise ValueError("Trailer points into the primary JPEG")
        ranges.append((start, start + length))
        blocks[name] = data[start:start + length]
    for previous, current in zip(sorted(ranges), sorted(ranges)[1:]):
        if previous[1] > current[0]:
            raise ValueError("Overlapping trailer blocks")
    return {"footer": data[-8:-4].decode("ascii"), "anchor": anchor,
            "start": min((start for start, _ in ranges), default=anchor),
            "index": index, "blocks": blocks}


def build_trailer(blocks, footer=b"jxrs"):
    if footer not in (b"jxrs", b"wtmk"):
        raise ValueError("Unknown footer")
    if "private.emptyspace" in blocks:
        raise ValueError("private.emptyspace is maintained by the writer")
    ordered = {"private.emptyspace": b"\0" * 4, **blocks}
    payload, positions = bytearray(), {}
    for name, value in ordered.items():
        if not isinstance(name, str) or not isinstance(value, bytes) or not value:
            raise ValueError("Blocks require nonempty bytes")
        positions[name] = len(payload)
        payload.extend(value)
    index = [{"name": name, "offset": len(payload) - positions[name], "length": len(value), "version": 1}
             for name, value in sorted(ordered.items())]
    encoded = json.dumps(index, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\0"
    total = len(payload) + len(encoded) + 8
    payload[:4] = struct.pack(">I", total)
    return bytes(payload) + encoded + footer + struct.pack("<I", len(encoded) + 8)


def inspect_bytes(data):
    end = jpeg_end(data)
    packets, has_mpf = [], False
    for marker, _, _, payload in headers(data):
        if marker == 0xE1 and payload.startswith(XMP_HEADER):
            try:
                packets.append(ET.fromstring(payload[len(XMP_HEADER):].rstrip(b"\0")))
            except ET.ParseError as exc:
                raise ValueError("Malformed XMP packet") from exc
        if marker == 0xE2 and payload.startswith(b"MPF\0"):
            has_mpf = True
    summary = {"primary_jpeg_bytes": end, "trailing_bytes": len(data) - end,
               "motion_photo": False, "has_gain_map": False, "has_mpf": has_mpf,
               "items": [], "primary_video_length": None, "motion_length_matches": False,
               "trailer": None}
    for packet in packets:
        for desc in packet.iter(q("rdf", "Description")):
            if desc.get(q("GCamera", "MotionPhoto")) == "1":
                summary["motion_photo"] = True
            if desc.get(q("OpCamera", "VideoLength")):
                summary["primary_video_length"] = int(desc.get(q("OpCamera", "VideoLength")))
        cursor = end
        for pos, item in enumerate(packet.iter(q("Container", "Item"))):
            semantic = item.get(q("Item", "Semantic"), "")
            length = int(item.get(q("Item", "Length"), "0"))
            padding = int(item.get(q("Item", "Padding"), "0"))
            if length < 0 or padding < 0:
                raise ValueError("Negative container length")
            summary["items"].append({"semantic": semantic, "length": length, "offset": 0 if pos == 0 else cursor})
            if semantic == "GainMap":
                summary["has_gain_map"] = True
            if semantic == "MotionPhoto":
                summary["motion_length_matches"] = (cursor + length == len(data)
                    and data[cursor + 4:cursor + 8] == b"ftyp")
            if pos:
                cursor += length
            cursor += padding
    trailer = parse_trailer(data)
    if trailer:
        blocks = trailer["blocks"]
        summary["trailer"] = {"footer": trailer["footer"], "block_names": sorted(blocks),
                              "block_lengths": {key: len(value) for key, value in blocks.items()}}
        mode = blocks.get("capture.mode", b"").rstrip(b"\0")
        summary["trailer"]["capture_mode"] = mode.decode() if mode in (b"master", b"photo", b"pro") else "uninterpreted"
        if "capture.info.backup" in blocks:
            # Do not expose original date, basename, GPS, or raw binary payloads.
            backup = json.loads(blocks["capture.info.backup"].rstrip(b"\0"))
            summary["trailer"]["has_original_date_backup"] = "originalDateTakenMs" in backup
            summary["trailer"]["has_original_filename_backup"] = "originalFileName" in backup
    summary["compound"] = bool(len(data) > end or summary["motion_photo"] or summary["has_gain_map"] or has_mpf)
    return summary


def make_motion_photo(image, video, blocks=None, timestamp_us=0, footer=b"jxrs", sub_video=None):
    if jpeg_end(image) != len(image) or inspect_bytes(image)["compound"]:
        raise ValueError("Build requires a plain JPEG, without old trailers or gain-map references")
    if video[4:8] != b"ftyp" or timestamp_us < 0:
        raise ValueError("Provide an MP4 and a nonnegative presentation timestamp")
    clean_blocks = dict(blocks or {})
    if sub_video is not None:
        if sub_video[4:8] != b"ftyp":
            raise ValueError("Sub-video must be MP4")
        clean_blocks.update({"live.subVideo": sub_video,
                             "live.subVideoSize": str(len(sub_video)).encode() + b"\0"})
    trailer = build_trailer(clean_blocks, footer) if clean_blocks else b""
    root = ET.Element(q("x", "xmpmeta"))
    rdf = ET.SubElement(root, q("rdf", "RDF"))
    desc = ET.SubElement(rdf, q("rdf", "Description"), {
        q("rdf", "about"): "", q("GCamera", "MotionPhoto"): "1", q("GCamera", "MotionPhotoVersion"): "1",
        q("GCamera", "MotionPhotoPresentationTimestampUs"): str(timestamp_us),
        q("OpCamera", "MotionPhotoPrimaryPresentationTimestampUs"): str(timestamp_us),
        q("OpCamera", "MotionPhotoOwner"): "oplus", q("OpCamera", "OLivePhotoVersion"): "2" if sub_video else "1",
        q("OpCamera", "VideoLength"): str(len(video))})
    seq = ET.SubElement(ET.SubElement(desc, q("Container", "Directory")), q("rdf", "Seq"))
    for semantic, mime, length in (("Primary", "image/jpeg", 0), ("MotionPhoto", "video/mp4", len(video) + len(trailer))):
        item = ET.SubElement(seq, q("rdf", "li"), {q("rdf", "parseType"): "Resource"})
        ET.SubElement(item, q("Container", "Item"), {q("Item", "Semantic"): semantic,
            q("Item", "Mime"): mime, q("Item", "Length"): str(length), q("Item", "Padding"): "0"})
    # ElementTree hoists declarations to xmpmeta. Semantically valid XML, but
    # ACE 3V gallery 16.40.22 failed to recognize it in a controlled comparison.
    # Keep escaped ET values while reproducing the observed camera scoping.
    xml = ET.tostring(root, encoding="utf-8")
    declarations = []
    for prefix in ("GCamera", "OpCamera", "Container", "Item", "rdf"):
        declaration = f' xmlns:{prefix}="{NS[prefix]}"'.encode()
        xml = xml.replace(declaration, b"", 1)
        if prefix == "rdf":
            xml = xml.replace(b"<rdf:RDF", b"<rdf:RDF" + declaration, 1)
        else:
            declarations.append(declaration)
    xml = xml.replace(b"<rdf:Description", b"<rdf:Description" + b"".join(declarations), 1)
    packet = XMP_HEADER + xml
    if len(packet) + 2 > 65535:
        raise ValueError("XMP exceeds one JPEG APP1 segment")
    # Plain image XMP (for example attribution) stays separate; no donor XMP imported.
    app1 = b"\xff\xe1" + struct.pack(">H", len(packet) + 2) + packet
    return image[:2] + app1 + image[2:] + video + trailer


def example_master_preset():
    """Rebuild one observed 496-byte settings layout using non-personal literals.

    The slot semantics are NOT fully decoded. This is an opt-in laboratory
    fixture, not a universal preset, and imports no bytes from a private photo.
    """
    data = bytearray(496)
    struct.pack_into("<fI", data, 0, 1.0, 100)
    data[12:16] = "无\0".encode("utf-8")
    struct.pack_into("<I", data, 132, 101)
    data[136:139] = b"13\0"
    data[236:243] = "美味\0".encode("utf-8")
    return bytes(data)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Structural summary, with private backup values omitted")
    inspect.add_argument("image", type=Path)
    build = sub.add_parser("build", help="Experimental new-scene JPEG + MP4 container; no donor import")
    build.add_argument("--image", type=Path, required=True)
    build.add_argument("--video", type=Path, required=True)
    build.add_argument("--sub-video", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--capture-mode", choices=("master", "photo", "pro"))
    build.add_argument("--example-master-preset", action="store_true", help="Opt-in observed settings fixture; undocumented slot semantics")
    build.add_argument("--footer", choices=("jxrs", "wtmk"), default="jxrs")
    build.add_argument("--presentation-us", type=int, default=0)
    build.add_argument("--oplus-flags", help="Observed feature mask, decimal or 0x hex; undocumented semantics")
    build.add_argument("--backup-time", help="Explicit synthetic/original date, ISO with UTC offset")
    build.add_argument("--backup-name", help="Explicit basename without directory")
    a = p.parse_args()
    if a.command == "inspect":
        print(json.dumps(inspect_bytes(a.image.read_bytes()), ensure_ascii=False, indent=2))
        return
    if a.output.exists():
        raise ValueError("Output already exists")
    image = a.image.read_bytes()
    if a.oplus_flags is not None:
        flags = int(a.oplus_flags, 0)
        if not 0 <= flags < 2**64:
            raise ValueError("Feature mask outside 64-bit range")
        from repair import exif
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new-scene.jpg"
            path.write_bytes(image)
            exif("exiftool", f"-ExifIFD:UserComment=oplus_{flags}", str(path))
            image = path.read_bytes()
    blocks = {"src.image": image}
    if a.capture_mode:
        blocks["capture.mode"] = a.capture_mode.encode() + b"\0"
    if a.example_master_preset:
        blocks["master.mode.preset.info"] = example_master_preset()
    if bool(a.backup_time) != bool(a.backup_name):
        raise ValueError("backup-time and backup-name must be supplied together")
    if a.backup_time:
        date = datetime.fromisoformat(a.backup_time)
        if date.tzinfo is None or not a.backup_name or any(c in a.backup_name for c in "/\\\n\r"):
            raise ValueError("Backup requires a timezone and a plain basename")
        blocks["capture.info.backup"] = json.dumps({"originalDateTakenMs": round(date.timestamp()*1000),
            "originalFileName": a.backup_name}, separators=(",", ":")).encode() + b"\0"
    result = make_motion_photo(image, a.video.read_bytes(), blocks, a.presentation_us,
                              a.footer.encode(), a.sub_video.read_bytes() if a.sub_video else None)
    summary = inspect_bytes(result)
    if not summary["motion_length_matches"]:
        raise ValueError("Constructed motion directory failed verification")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("xb") as stream:
        stream.write(result)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
