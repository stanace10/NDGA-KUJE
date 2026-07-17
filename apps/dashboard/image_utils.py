from __future__ import annotations

from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile


def optimize_public_upload(
    uploaded_file: UploadedFile | None,
    *,
    max_size: tuple[int, int] = (1800, 1200),
    quality: int = 82,
):
    if not uploaded_file:
        return uploaded_file
    if not isinstance(uploaded_file, UploadedFile):
        return uploaded_file

    try:
        from PIL import Image, ImageOps

        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
        if getattr(image, "is_animated", False):
            uploaded_file.seek(0)
            return uploaded_file

        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background

        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="WEBP", quality=quality, method=6)
        buffer.seek(0)
        filename = f"{Path(uploaded_file.name).stem}.webp"
        return ContentFile(buffer.read(), name=filename)
    except Exception:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return uploaded_file
