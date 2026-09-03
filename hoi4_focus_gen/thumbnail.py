from __future__ import annotations

from pathlib import Path

from PIL import Image

THUMBNAIL_SIZE = 512


def create_thumbnail(source: Path, destination: Path, size: int = THUMBNAIL_SIZE) -> None:
    image = Image.open(source).convert("RGBA")
    if image.width == 0 or image.height == 0:
        raise ValueError(f"Invalid image: {source}")
    scale = min(size / image.width, size / image.height)
    new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - resized.width) // 2, (size - resized.height) // 2)
    canvas.paste(resized, offset, resized)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG")
