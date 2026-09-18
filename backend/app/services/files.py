import io
from pathlib import PurePath

from fastapi import HTTPException
from PIL import Image

Image.MAX_IMAGE_PIXELS = 20_000_000


async def read_upload(upload, limit):
    chunks, size = [], 0
    while chunk := await upload.read(65536):
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, "File exceeds the 10 MB upload limit.")
        chunks.append(chunk)
    await upload.close()
    if not size:
        raise HTTPException(422, "The uploaded file is empty.")
    return b"".join(chunks)


def safe_name(name):
    name = PurePath((name or "upload").replace("\\", "/")).name
    return "".join(c for c in name if c.isalnum() or c in " ._-")[:120] or "upload"


def document_type(data):
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > 20_000_000:
            raise ValueError("Too many pixels")
        image.verify()
        if image.format not in ("JPEG", "PNG"):
            raise ValueError("Unsupported image")
        return "image/png" if image.format == "PNG" else "image/jpeg"
    except Exception:
        raise HTTPException(415, "Upload a valid PDF, JPG, or PNG document.") from None


def audio_type(data):
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav", "wav"
    if data[:4] == b"\x1aE\xdf\xa3":
        return "audio/webm", "webm"
    if data[:4] == b"OggS":
        return "audio/ogg", "ogg"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg", "mp3"
    if data[4:8] == b"ftyp":
        return "audio/mp4", "m4a"
    if data[:4] == b"fLaC":
        return "audio/flac", "flac"
    raise HTTPException(415, "Use WAV, WebM, OGG, MP3, M4A, or FLAC audio.")
