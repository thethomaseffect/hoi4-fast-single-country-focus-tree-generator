from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageOps

THUMBNAIL_SIZE = 512
FLAG_SIZE = (82, 52)
FLAG_ASPECT = FLAG_SIZE[0] / FLAG_SIZE[1]
FLAG_ASPECT_TOLERANCE = 0.03
DEFAULT_TEMPLATE_ALIAS = "vanilla"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def templates_dir() -> Path:
    return repo_root() / "assets" / "thumbnail_templates"


def flag_aspect_ratio_ok(size: tuple[int, int]) -> bool:
    width, height = size
    if width <= 0 or height <= 0:
        return False
    return abs(width / height - FLAG_ASPECT) <= FLAG_ASPECT_TOLERANCE


def flag_slot_rect(
    template_path: Path | None = None, size: int = THUMBNAIL_SIZE
) -> tuple[int, int, int, int]:
    width, height = FLAG_SIZE
    origin_x = (size - width) // 2
    origin_y = (size - height) // 2
    if template_path is not None:
        meta = template_path.with_suffix(".json")
        if meta.is_file():
            data = json.loads(meta.read_text(encoding="utf-8"))
            origin_x = int(data.get("flag_x", origin_x))
            origin_y = int(data.get("flag_y", origin_y))
            width = int(data.get("flag_w", width))
            height = int(data.get("flag_h", height))
    return origin_x, origin_y, width, height


def _require_size(image: Image.Image, expected: tuple[int, int], label: str, path: Path) -> None:
    if image.size != expected:
        raise ValueError(
            f"{label} must be {expected[0]}x{expected[1]} pixels, "
            f"got {image.size[0]}x{image.size[1]}: {path}"
        )


def _require_flag_aspect(image: Image.Image, path: Path) -> None:
    if not flag_aspect_ratio_ok(image.size):
        raise ValueError(
            f"Country flag must be a rectangle with HOI4 flag aspect "
            f"{FLAG_SIZE[0]}:{FLAG_SIZE[1]}, got {image.size[0]}x{image.size[1]}: {path}"
        )


def _open_rgba(path: Path) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    return Image.open(path).convert("RGBA")


def template_alias(stem: str) -> str | None:
    """Map template_vanilla.png -> vanilla, template_owb.png -> owb."""
    parts = stem.split("_", 1)
    if len(parts) == 2 and parts[0].lower() == "template" and parts[1]:
        return parts[1].lower()
    return None


def bundled_templates() -> dict[str, Path]:
    found: dict[str, Path] = {}
    folder = templates_dir()
    if not folder.is_dir():
        return found
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in {".png", ".tga", ".jpg", ".jpeg"}:
            continue
        alias = template_alias(path.stem)
        if alias is None:
            continue
        found[alias] = path
    return found


def _alias_key(value: str) -> str:
    key = value.strip().lower()
    prefix = "template_"
    if key.startswith(prefix):
        return key[len(prefix) :]
    return key


def resolve_thumbnail_template(value: str | None) -> Path:
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_file():
            return candidate
        templates = bundled_templates()
        key = _alias_key(value)
        if key in templates:
            return templates[key]
        names = ", ".join(sorted(templates))
        raise FileNotFoundError(
            f"Thumbnail template {value!r} is not a file and does not match a bundled "
            f"template ({names})."
        )
    templates = bundled_templates()
    if DEFAULT_TEMPLATE_ALIAS in templates:
        return templates[DEFAULT_TEMPLATE_ALIAS]
    raise FileNotFoundError(
        f"Default thumbnail template {DEFAULT_TEMPLATE_ALIAS!r} was not found in {templates_dir()}"
    )


def write_custom_thumbnail(source: Path, destination: Path) -> None:
    image = _open_rgba(source)
    _require_size(image, (THUMBNAIL_SIZE, THUMBNAIL_SIZE), "Custom thumbnail", source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG")


def write_templated_thumbnail(
    template_path: Path,
    flag_path: Path,
    destination: Path,
) -> None:
    template = _open_rgba(template_path)
    _require_size(template, (THUMBNAIL_SIZE, THUMBNAIL_SIZE), "Thumbnail template", template_path)
    flag = _open_rgba(flag_path)
    _require_flag_aspect(flag, flag_path)
    origin_x, origin_y, slot_w, slot_h = flag_slot_rect(template_path)
    flag = ImageOps.fit(flag, (slot_w, slot_h), method=Image.Resampling.LANCZOS)
    canvas = template.copy()
    canvas.paste(flag, (origin_x, origin_y), flag)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG")
