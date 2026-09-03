from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


DEFAULT_FOCUS_TIME = 0
YAML_FILENAMES = ("options.yaml", "options.yml")


@dataclass
class Options:
    country_tags: list[str] = field(default_factory=list)
    all_countries: bool = False
    save_game_location: Path | None = None
    playset: str | None = None
    add_to_playlist: str | None = None
    add_to_playlist_enabled: bool = True
    focus_time: float = DEFAULT_FOCUS_TIME
    thumbnail: Path | None = None
    hoi4_documents: Path | None = None
    workshop_content: Path | None = None
    hoi4_install: Path | None = None
    mods_directory: Path | None = None


def _as_path(value: Any) -> Path | None:
    if value is None or value == "":
        return None
    return Path(str(value)).expanduser()


def _as_tags(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return [part.strip().upper() for part in str(value).split(",") if part.strip()]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _yaml_has_values(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return True
    return False


def load_yaml_options(search_dir: Path) -> dict[str, Any]:
    for name in YAML_FILENAMES:
        path = search_dir / name
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if not _yaml_has_values(text):
                return {}
            if yaml is None:
                raise RuntimeError(
                    f"Found {path.name} but PyYAML is not installed. "
                    "Run: pip install -r requirements.txt"
                )
            data = yaml.safe_load(text) or {}
            if not isinstance(data, dict):
                raise ValueError(f"{path} must contain a YAML mapping")
            return data
    return {}


def options_from_yaml(data: dict[str, Any]) -> Options:
    add_to_playlist = data.get("add_to_playlist")
    add_enabled = True
    playlist_name: str | None = None
    if isinstance(add_to_playlist, bool):
        add_enabled = add_to_playlist
    elif add_to_playlist is not None and str(add_to_playlist).strip() != "":
        playlist_name = str(add_to_playlist).strip()

    focus_time = data.get("focus_time", DEFAULT_FOCUS_TIME)
    if focus_time is None or focus_time == "":
        focus_time = DEFAULT_FOCUS_TIME

    return Options(
        country_tags=_as_tags(data.get("country_tags")),
        all_countries=_as_bool(data.get("all_countries", False)),
        save_game_location=_as_path(data.get("save_game_location")),
        playset=str(data["playset"]).strip() if data.get("playset") else None,
        add_to_playlist=playlist_name,
        add_to_playlist_enabled=add_enabled,
        focus_time=float(focus_time),
        thumbnail=_as_path(data.get("thumbnail")),
        hoi4_documents=_as_path(data.get("hoi4_documents")),
        workshop_content=_as_path(data.get("workshop_content")),
        hoi4_install=_as_path(data.get("hoi4_install")),
        mods_directory=_as_path(data.get("mods_directory")),
    )


def merge_options(yaml_opts: Options, cli: Options) -> Options:
    """CLI values win when they were explicitly provided (non-empty / non-None)."""
    return Options(
        country_tags=cli.country_tags or yaml_opts.country_tags,
        all_countries=cli.all_countries or yaml_opts.all_countries,
        save_game_location=cli.save_game_location or yaml_opts.save_game_location,
        playset=cli.playset or yaml_opts.playset,
        add_to_playlist=cli.add_to_playlist or yaml_opts.add_to_playlist,
        add_to_playlist_enabled=(
            cli.add_to_playlist_enabled
            if cli.add_to_playlist_enabled is False
            else yaml_opts.add_to_playlist_enabled
        ),
        focus_time=cli.focus_time if cli.focus_time != DEFAULT_FOCUS_TIME or yaml_opts.focus_time == DEFAULT_FOCUS_TIME else yaml_opts.focus_time,
        thumbnail=cli.thumbnail or yaml_opts.thumbnail,
        hoi4_documents=cli.hoi4_documents or yaml_opts.hoi4_documents,
        workshop_content=cli.workshop_content or yaml_opts.workshop_content,
        hoi4_install=cli.hoi4_install or yaml_opts.hoi4_install,
        mods_directory=cli.mods_directory or yaml_opts.mods_directory,
    )
