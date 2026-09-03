from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

STEAM_APP_ID = "394360"
GAME_FOLDER_NAME = "Hearts of Iron IV"
DOCUMENTS_GAME = Path("Paradox Interactive") / "Hearts of Iron IV"


@dataclass(frozen=True)
class GamePaths:
    documents: Path
    mods: Path
    save_games: Path
    playsets_backup: Path
    launcher_db: Path
    continue_game: Path
    dlc_load: Path
    workshop: Path
    install: Path

    @property
    def vanilla_national_focus(self) -> Path:
        return self.install / "common" / "national_focus"

    @property
    def vanilla_country_tags(self) -> Path:
        return self.install / "common" / "country_tags"

    @property
    def vanilla_flags(self) -> Path:
        return self.install / "gfx" / "flags"

    @property
    def launcher_settings(self) -> Path:
        return self.install / "launcher-settings.json"


def _windows_documents() -> Path:
    home = Path.home()
    candidates = [
        home / "Documents",
        home / "OneDrive" / "Documents",
        Path(os.environ.get("USERPROFILE", str(home))) / "Documents",
    ]
    for candidate in candidates:
        documents_game = candidate / DOCUMENTS_GAME
        if documents_game.is_dir():
            return documents_game
    return home / "Documents" / DOCUMENTS_GAME


def _parse_vdf_paths(vdf_text: str) -> list[Path]:
    paths: list[Path] = []
    for match in re.finditer(r'"path"\s*"([^"]+)"', vdf_text):
        paths.append(Path(match.group(1).replace("\\\\", "\\")))
    return paths


def find_steam_libraries() -> list[Path]:
    libraries: list[Path] = []
    default_steam = Path(r"C:\Program Files (x86)\Steam")
    if sys.platform != "win32":
        default_steam = Path.home() / ".steam" / "steam"
    vdf = default_steam / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        libraries.extend(_parse_vdf_paths(vdf.read_text(encoding="utf-8", errors="replace")))
    if default_steam not in libraries:
        libraries.insert(0, default_steam)
    return libraries


def find_hoi4_install(explicit: Path | None = None) -> Path:
    if explicit and explicit.is_dir():
        return explicit
    for library in find_steam_libraries():
        candidate = library / "steamapps" / "common" / GAME_FOLDER_NAME
        if candidate.is_dir() and (
            (candidate / "hoi4.exe").exists()
            or (candidate / "launcher-settings.json").exists()
        ):
            return candidate
    fallback = Path(r"C:\Program Files (x86)\Steam\steamapps\common") / GAME_FOLDER_NAME
    return fallback


def find_workshop(explicit: Path | None = None, install: Path | None = None) -> Path:
    if explicit and explicit.is_dir():
        return explicit
    if install:
        # .../common/Hearts of Iron IV -> .../workshop/content/394360
        steamapps = install.parent.parent
        workshop = steamapps / "workshop" / "content" / STEAM_APP_ID
        if workshop.is_dir():
            return workshop
    for library in find_steam_libraries():
        workshop = library / "steamapps" / "workshop" / "content" / STEAM_APP_ID
        if workshop.is_dir():
            return workshop
    return Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content") / STEAM_APP_ID


def resolve_paths(
    documents: Path | None = None,
    mods_directory: Path | None = None,
    save_game_location: Path | None = None,
    workshop_content: Path | None = None,
    hoi4_install: Path | None = None,
) -> GamePaths:
    docs = documents or _windows_documents()
    install = find_hoi4_install(hoi4_install)
    workshop = find_workshop(workshop_content, install)
    return GamePaths(
        documents=docs,
        mods=mods_directory or docs / "mod",
        save_games=save_game_location or docs / "save games",
        playsets_backup=docs / "playsets_backup",
        launcher_db=docs / "launcher-v2.sqlite",
        continue_game=docs / "continue_game.json",
        dlc_load=docs / "dlc_load.json",
        workshop=workshop,
        install=install,
    )


def game_supported_version(paths: GamePaths) -> str:
    settings = paths.launcher_settings
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            raw = data.get("rawVersion")
            if raw:
                return str(raw)
        except json.JSONDecodeError:
            pass
    return "1.19.*"


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return cleaned.strip("_") or "mod"
