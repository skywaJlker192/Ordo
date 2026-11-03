"""Определение типа файла по содержимому (сигнатурам), а не только по расширению."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

_EXT_KINDS = {
    "image": "jpg jpeg jpe png gif webp bmp tif tiff svg ico heic heif avif",
    "video": "mp4 mkv avi mov wmv flv webm m4v 3gp mpg mpeg",
    "audio": "mp3 wav flac ogg m4a aac wma opus",
    "document": (
        "pdf doc docx docm xls xlsx xlsm ppt pptx odt ods odp txt rtf csv md "
        "epub fb2 djvu"
    ),
    "archive": "zip rar 7z tar gz tgz bz2 xz iso",
    "installer": "exe msi apk dmg deb",
    "code": (
        "py js ts html css json xml c cpp h cs java go rs php sql sh bat ps1 "
        "ipynb yml yaml toml"
    ),
}
EXT_TO_KIND = {e: k for k, exts in _EXT_KINDS.items() for e in exts.split()}

# ZIP-контейнеры, у которых расширение настоящее, хотя внутри zip
_ZIP_BASED = set(
    "docx xlsx pptx docm xlsm pptm dotx xltx odt ods odp epub apk aab jar "
    "xpi crx vsdx xps whl nupkg 3mf".split()
)

# расширения-синонимы: не считаем это «подменой»
_SAME_GROUPS = [
    {"jpg", "jpeg", "jpe"},
    {"tif", "tiff"},
    {"mkv", "webm"},
    {"mp4", "mov", "m4v", "3gp"},
    {"gz", "tgz"},
    {"heic", "heif"},
]

_SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", "png", "image"),
    (b"\xff\xd8\xff", "jpg", "image"),
    (b"GIF87a", "gif", "image"),
    (b"GIF89a", "gif", "image"),
    (b"BM", "bmp", "image"),
    (b"%PDF-", "pdf", "document"),
    (b"Rar!\x1a\x07", "rar", "archive"),
    (b"7z\xbc\xaf\x27\x1c", "7z", "archive"),
    (b"\x1f\x8b", "gz", "archive"),
    (b"ID3", "mp3", "audio"),
    (b"OggS", "ogg", "audio"),
    (b"fLaC", "flac", "audio"),
    (b"\x1aE\xdf\xa3", "mkv", "video"),
]


@dataclass(frozen=True)
class FileKind:
    kind: str          # image / video / audio / document / archive / installer / code / other
    real_ext: str      # расширение, соответствующее содержимому
    by_content: bool   # тип определён по сигнатуре, а не по расширению


def kind_from_ext(ext: str) -> str:
    return EXT_TO_KIND.get(ext, "other")


def same_ext(a: str, b: str) -> bool:
    return a == b or any(a in g and b in g for g in _SAME_GROUPS)


def _sniff(head: bytes, ext: str) -> Optional[Tuple[str, str]]:
    if len(head) >= 12 and head.startswith(b"RIFF"):
        sub = head[8:12]
        if sub == b"WEBP":
            return "webp", "image"
        if sub == b"WAVE":
            return "wav", "audio"
        if sub == b"AVI ":
            return "avi", "video"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "m4a", "audio"
        if brand in (b"heic", b"heix", b"mif1"):
            return "heic", "image"
        return (ext if ext in ("mov", "m4v", "3gp") else "mp4"), "video"
    if head.startswith(b"PK\x03\x04"):
        if ext in _ZIP_BASED:
            return ext, kind_from_ext(ext)
        return "zip", "archive"
    if head.startswith(b"\xd0\xcf\x11\xe0"):  # старый формат MS Office / MSI
        if ext == "msi":
            return "msi", "installer"
        if ext in ("doc", "xls", "ppt"):
            return ext, "document"
        return "doc", "document"
    if head.startswith(b"MZ"):
        if ext == "dll":
            return "dll", "other"
        return "exe", "installer"
    for sig, real_ext, kind in _SIGNATURES:
        if head.startswith(sig):
            if real_ext == "mkv" and ext == "webm":
                return "webm", "video"
            return real_ext, kind
    return None


def detect(path: Path) -> FileKind:
    ext = path.suffix.lower().lstrip(".")
    head = b""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        pass
    hit = _sniff(head, ext) if head else None
    if hit:
        real_ext, kind = hit
        return FileKind(kind, real_ext, True)
    return FileKind(kind_from_ext(ext), ext, False)
