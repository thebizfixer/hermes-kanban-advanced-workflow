"""UTF-8 text reads for plugin file materialization."""

from __future__ import annotations

from pathlib import Path


def repair_legacy_text_bytes(data: bytes) -> bytes:
    """Normalize common mojibake and lone Latin-1 section bytes to valid UTF-8."""
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i : i + 6] == b"\xc3\xa2\xc2\x80\xc2\x94":
            out.extend("\u2014".encode("utf-8"))
            i += 6
            continue
        if data[i : i + 6] == b"\xc3\xa2\xc2\x80\xc2\x93":
            out.extend("\u2013".encode("utf-8"))
            i += 6
            continue
        if data[i : i + 6] == b"\xc3\xa2\xc2\x86\xc2\x92":
            out.extend(b"->")
            i += 6
            continue
        if data[i : i + 4] == b"\xc3\x82\xc2\xa7":
            out.extend("\u00a7".encode("utf-8"))
            i += 4
            continue
        if data[i] == 0xA7 and (i == 0 or data[i - 1] != 0xC2):
            out.extend("\u00a7".encode("utf-8"))
            i += 1
            continue
        out.append(data[i])
        i += 1
    return bytes(out)


def read_utf8_text(path: Path) -> str:
    """Read a text file as UTF-8, repairing legacy encodings when needed."""
    data = path.read_bytes()
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return repair_legacy_text_bytes(data).decode("utf-8")
