from __future__ import annotations

import json
import sqlite3
import time
import uuid
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from hoi4_focus_gen.paths import GamePaths, slugify
from hoi4_focus_gen.pdx import (
    CountryEval,
    FocusTreeInfo,
    country_tags_from_text,
    focus_trees_in_file,
    parse_descriptor_file,
    parse_pdx_file,
    read_pdx_text,
)

NATIONAL_FOCUS_DIR = "common/national_focus"
COUNTRY_TAGS_DIR = "common/country_tags"
FLAGS_DIR = "gfx/flags"


@dataclass
class PlaysetMod:
    id: str
    display_name: str
    steam_id: str | None
    source: str
    dir_path: Path
    game_registry_id: str | None
    required_version: str | None
    position: int
    enabled: bool
    replace_paths: set[str] = field(default_factory=set)

    @property
    def slug(self) -> str:
        return slugify(self.display_name)

    @property
    def is_generated_focus_mod(self) -> bool:
        display = (self.display_name or "").lower()
        folder = self.dir_path.name.lower()
        registry = (self.game_registry_id or "").lower()
        return (
            display.endswith(" focus tree edited")
            or folder.endswith("_focus_tree_edited")
            or registry.endswith("_focus_tree_edited.mod")
        )


@dataclass
class Playset:
    id: str
    name: str
    is_active: bool
    mods: list[PlaysetMod]


@dataclass
class LoadedFocusFile:
    relative_name: str
    path: Path
    source_name: str
    source_mod: PlaysetMod | None


def _connect(paths: GamePaths) -> sqlite3.Connection:
    if not paths.launcher_db.is_file():
        raise FileNotFoundError(f"Launcher database not found: {paths.launcher_db}")
    conn = sqlite3.connect(paths.launcher_db)
    conn.row_factory = sqlite3.Row
    return conn


def _descriptor_paths(mod: PlaysetMod, paths: GamePaths) -> list[Path]:
    found: list[Path] = []
    if mod.game_registry_id:
        found.append(paths.documents / Path(*mod.game_registry_id.split("/")))
    found.append(mod.dir_path / "descriptor.mod")
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def enrich_mod_descriptors(mod: PlaysetMod, paths: GamePaths) -> None:
    replace_paths: set[str] = set()
    for path in _descriptor_paths(mod, paths):
        info = parse_descriptor_file(path)
        if info:
            replace_paths.update(info.replace_paths)
            if not mod.required_version and info.supported_version:
                mod.required_version = info.supported_version
            if info.name and not mod.display_name:
                mod.display_name = info.name
    mod.replace_paths = replace_paths


def load_playset(paths: GamePaths, playset_name: str | None = None) -> Playset:
    conn = _connect(paths)
    try:
        if playset_name:
            row = conn.execute(
                "SELECT id, name, isActive FROM playsets WHERE name = ? COLLATE NOCASE",
                (playset_name,),
            ).fetchone()
            if row is None:
                names = [r["name"] for r in conn.execute("SELECT name FROM playsets")]
                raise ValueError(f"Playset {playset_name!r} not found. Available: {names}")
        else:
            row = conn.execute(
                "SELECT id, name, isActive FROM playsets WHERE isActive = 1"
            ).fetchone()
            if row is None:
                row = conn.execute("SELECT id, name, isActive FROM playsets").fetchone()
            if row is None:
                raise ValueError("No playsets found in launcher-v2.sqlite")

        mods: list[PlaysetMod] = []
        query = """
            SELECT m.id, m.displayName, m.steamId, m.source, m.dirPath,
                   m.gameRegistryId, m.requiredVersion, pm.position, pm.enabled
            FROM playsets_mods pm
            JOIN mods m ON m.id = pm.modId
            WHERE pm.playsetId = ?
            ORDER BY pm.position
        """
        for item in conn.execute(query, (row["id"],)):
            if not item["enabled"]:
                continue
            dir_path = Path(item["dirPath"]) if item["dirPath"] else Path()
            mod = PlaysetMod(
                id=item["id"],
                display_name=item["displayName"] or dir_path.name,
                steam_id=item["steamId"],
                source=item["source"] or "",
                dir_path=dir_path,
                game_registry_id=item["gameRegistryId"],
                required_version=item["requiredVersion"],
                position=item["position"] or 0,
                enabled=bool(item["enabled"]),
            )
            enrich_mod_descriptors(mod, paths)
            mods.append(mod)
        return Playset(id=row["id"], name=row["name"], is_active=bool(row["isActive"]), mods=mods)
    finally:
        conn.close()


def _folder_files(folder: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not folder.is_dir():
        return files
    for path in folder.rglob("*"):
        if path.is_file():
            files[path.name] = path
    return files


def resolve_game_files(
    paths: GamePaths,
    playset: Playset,
    relative_dir: str,
) -> dict[str, LoadedFocusFile]:
    """Apply vanilla + playset load order, honoring replace_path and same-name overwrites."""
    loaded: dict[str, LoadedFocusFile] = {}
    vanilla_dir = paths.install / Path(*relative_dir.split("/"))
    if vanilla_dir.is_dir():
        for name, path in _folder_files(vanilla_dir).items():
            loaded[name] = LoadedFocusFile(name, path, "vanilla", None)

    for mod in playset.mods:
        if mod.is_generated_focus_mod:
            continue
        if relative_dir in mod.replace_paths:
            loaded.clear()
        mod_dir = mod.dir_path / Path(*relative_dir.split("/"))
        if not mod_dir.is_dir():
            continue
        for name, path in _folder_files(mod_dir).items():
            loaded[name] = LoadedFocusFile(name, path, mod.display_name, mod)
    return loaded


def resolve_country_tags(paths: GamePaths, playset: Playset) -> list[str]:
    files = resolve_game_files(paths, playset, COUNTRY_TAGS_DIR)
    tags: list[str] = []
    seen: set[str] = set()
    for loaded in files.values():
        for tag in country_tags_from_text(read_pdx_text(loaded.path)):
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags


@dataclass
class CountryFocusPlan:
    tag: str
    files: list[LoadedFocusFile]
    last_mod: PlaysetMod | None
    last_mod_name: str
    dependencies: list[str]
    tree_ids: list[str]


def focus_altering_mods(playset: Playset) -> list[PlaysetMod]:
    return [
        mod
        for mod in playset.mods
        if not mod.is_generated_focus_mod
        and (
            NATIONAL_FOCUS_DIR in mod.replace_paths
            or (mod.dir_path / "common" / "national_focus").is_dir()
        )
    ]


def _pick_assigned_tree(
    loaded_files: dict[str, LoadedFocusFile],
    country: CountryEval,
) -> tuple[LoadedFocusFile, FocusTreeInfo] | None:
    scored: list[tuple[float, int, LoadedFocusFile, FocusTreeInfo]] = []
    load_index = 0
    for loaded in loaded_files.values():
        try:
            root = parse_pdx_file(loaded.path)
        except Exception:
            continue
        for tree in focus_trees_in_file(root):
            scored.append((tree.score(country), load_index, loaded, tree))
            load_index += 1
    if not scored:
        return None
    best_score = max(item[0] for item in scored)
    if best_score > 0:
        winner = max((item for item in scored if item[0] == best_score), key=lambda item: item[1])
        return winner[2], winner[3]
    defaults = [item for item in scored if item[3].is_default]
    if defaults:
        winner = defaults[-1]
        return winner[2], winner[3]
    return None


def plan_country_focus(
    paths: GamePaths,
    playset: Playset,
    tag: str,
    loaded_files: dict[str, LoadedFocusFile] | None = None,
    overlord: str | None = None,
) -> CountryFocusPlan | None:
    loaded_files = loaded_files or resolve_game_files(paths, playset, NATIONAL_FOCUS_DIR)
    tag = tag.upper()
    country = CountryEval(tag=tag, original_tag=tag, overlord=overlord)
    picked = _pick_assigned_tree(loaded_files, country)
    if picked is None:
        return None
    loaded, tree = picked
    last_mod = loaded.source_mod
    last_mod_name = loaded.source_mod.display_name if loaded.source_mod else loaded.source_name
    return CountryFocusPlan(
        tag=tag,
        files=[loaded],
        last_mod=last_mod,
        last_mod_name=last_mod_name,
        dependencies=[mod.display_name for mod in focus_altering_mods(playset)],
        tree_ids=[tree.tree_id] if tree.tree_id else [],
    )


def find_flag_path(paths: GamePaths, playset: Playset, tag: str) -> Path | None:
    tag = tag.upper()
    names = [
        f"{tag}.tga",
        f"{tag}.png",
        f"{tag}.dds",
        f"{tag}_neutrality.tga",
        f"{tag}_democratic.tga",
        f"{tag}_fascism.tga",
        f"{tag}_communism.tga",
    ]
    search_roots: list[Path] = []
    for mod in reversed(playset.mods):
        search_roots.append(mod.dir_path / "gfx" / "flags")
    search_roots.append(paths.vanilla_flags)

    for root in search_roots:
        if not root.is_dir():
            continue
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
        matches = sorted(root.glob(f"{tag}*.tga"))
        if matches:
            return matches[0]
    return None


def _first_quoted_string(data: bytes) -> str | None:
    """HOI4bin string token: 0x0F 0x00, uint16 length, then bytes."""
    i = 0
    while i + 5 < len(data):
        if data[i] == 0x0F and data[i + 1] == 0x00:
            length = int.from_bytes(data[i + 2 : i + 4], "little")
            start = i + 4
            end = start + length
            if 2 <= length <= 4 and end <= len(data):
                try:
                    value = data[start:end].decode("ascii")
                except UnicodeDecodeError:
                    i += 1
                    continue
                if value.isalpha() and value.isupper():
                    return value
            i = end
            continue
        i += 1
    return None


def player_tag_from_save(save_path: Path) -> str | None:
    if not save_path.is_file():
        return None
    header = save_path.read_bytes()[: 64 * 1024]
    if header.startswith(b"HOI4bin"):
        return _first_quoted_string(header[7:])
    if header.startswith(b"HOI4txt") or b"player=" in header[:4096]:
        text = header.decode("utf-8", errors="replace")
        match = __import__("re").search(r"\bplayer\s*=\s*([A-Z0-9]{2,4})\b", text)
        if match:
            return match.group(1)
    stem = save_path.stem
    prefix = stem.split("_")[0]
    if prefix.isalpha() and 2 <= len(prefix) <= 4:
        return prefix.upper()
    return None


def latest_save_tag(paths: GamePaths, save_game_location: Path | None = None) -> tuple[str, Path | None]:
    save_dir = save_game_location or paths.save_games
    continue_path = paths.continue_game
    if continue_path.is_file():
        try:
            data = json.loads(continue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        filename = data.get("filename")
        if filename:
            save_path = save_dir / filename
            tag = player_tag_from_save(save_path)
            if tag:
                return tag, save_path
            stem = Path(str(filename)).stem
            prefix = stem.split("_")[0]
            if prefix.isalpha() and 2 <= len(prefix) <= 4:
                return prefix.upper(), save_path if save_path.is_file() else None

    if save_dir.is_dir():
        saves = [p for p in save_dir.glob("*.hoi4") if p.is_file()]
        saves.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for save_path in saves:
            tag = player_tag_from_save(save_path)
            if tag:
                return tag, save_path
    raise FileNotFoundError(
        f"Could not determine a country tag from continue_game.json or saves in {save_dir}"
    )


def generated_mod_folder_name(last_mod_name: str, tag: str) -> str:
    return f"{slugify(last_mod_name)}_{tag.lower()}_focus_tree_edited"


def generated_mod_display_name(tag: str) -> str:
    return f"{tag} Focus Tree Edited"


def remove_local_mod_files(paths: GamePaths, folder_name: str) -> None:
    folder = paths.mods / folder_name
    if folder.is_dir():
        shutil.rmtree(folder)
    registry = paths.mods / f"{folder_name}.mod"
    if registry.is_file():
        registry.unlink()


def unregister_local_mod(paths: GamePaths, folder_name: str) -> None:
    registry_id = f"mod/{folder_name}.mod"
    dir_path = str(paths.mods / folder_name)
    conn = _connect(paths)
    try:
        rows = conn.execute(
            "SELECT id FROM mods WHERE gameRegistryId = ? OR dirPath = ?",
            (registry_id, dir_path),
        ).fetchall()
        for row in rows:
            conn.execute("DELETE FROM playsets_mods WHERE modId = ?", (row["id"],))
            conn.execute("DELETE FROM mods WHERE id = ?", (row["id"],))
        conn.commit()
    finally:
        conn.close()
    if paths.dlc_load.is_file():
        try:
            data = json.loads(paths.dlc_load.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
        if data is not None:
            enabled = [item for item in (data.get("enabled_mods") or []) if item != registry_id]
            if enabled != data.get("enabled_mods"):
                data["enabled_mods"] = enabled
                paths.dlc_load.write_text(json.dumps(data, indent=2), encoding="utf-8")


def stale_generated_folders(paths: GamePaths, tag: str, keep_folder: str) -> list[str]:
    suffix = f"_{tag.lower()}_focus_tree_edited"
    found: list[str] = []
    if not paths.mods.is_dir():
        return found
    for path in paths.mods.iterdir():
        if path.is_dir() and path.name.endswith(suffix) and path.name != keep_folder:
            found.append(path.name)
    return found


def register_local_mod(
    paths: GamePaths,
    playset: Playset,
    folder_name: str,
    display_name: str,
    supported_version: str,
    thumbnail_path: Path,
) -> None:
    conn = _connect(paths)
    registry_id = f"mod/{folder_name}.mod"
    dir_path = str(paths.mods / folder_name)
    now = int(time.time())
    try:
        existing = conn.execute(
            "SELECT id FROM mods WHERE gameRegistryId = ? OR dirPath = ?",
            (registry_id, dir_path),
        ).fetchone()
        if existing:
            mod_id = existing["id"]
            conn.execute(
                """
                UPDATE mods
                SET displayName = ?, version = ?, tags = ?, requiredVersion = ?,
                    dirPath = ?, gameRegistryId = ?, status = ?, source = ?,
                    thumbnailPath = ?, timeUpdated = ?, keepLatest = 1
                WHERE id = ?
                """,
                (
                    display_name,
                    "1.0",
                    '["National Focuses","Utilities"]',
                    supported_version,
                    dir_path,
                    registry_id,
                    "ready_to_play",
                    "local",
                    str(thumbnail_path),
                    now,
                    mod_id,
                ),
            )
        else:
            mod_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO mods (
                    id, gameRegistryId, displayName, version, tags, requiredVersion,
                    dirPath, status, source, cause, isNew, createdDate, size,
                    isMetadataApplied, metadataStatus, keepLatest, thumbnailPath, timeUpdated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mod_id,
                    registry_id,
                    display_name,
                    "1.0",
                    '["National Focuses","Utilities"]',
                    supported_version,
                    dir_path,
                    "ready_to_play",
                    "local",
                    "",
                    0,
                    now,
                    0,
                    0,
                    "not_applied",
                    1,
                    str(thumbnail_path),
                    now,
                ),
            )

        link = conn.execute(
            "SELECT enabled, position FROM playsets_mods WHERE playsetId = ? AND modId = ?",
            (playset.id, mod_id),
        ).fetchone()
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM playsets_mods WHERE playsetId = ?",
            (playset.id,),
        ).fetchone()[0]
        if link:
            conn.execute(
                """
                UPDATE playsets_mods
                SET enabled = 1, position = ?
                WHERE playsetId = ? AND modId = ?
                """,
                (max_pos if link["position"] == max_pos else max_pos + 1, playset.id, mod_id),
            )
            if link["position"] != max_pos:
                # already at bottom if position == max; otherwise move after current max
                pass
        else:
            conn.execute(
                "INSERT INTO playsets_mods (playsetId, modId, enabled, position) VALUES (?, ?, 1, ?)",
                (playset.id, mod_id, max_pos + 1),
            )
        conn.execute(
            "UPDATE playsets SET updatedOn = ? WHERE id = ?",
            (int(time.time() * 1000), playset.id),
        )
        conn.commit()
    finally:
        conn.close()


def update_dlc_load(paths: GamePaths, folder_name: str) -> None:
    registry = f"mod/{folder_name}.mod"
    if not paths.dlc_load.is_file():
        return
    try:
        data = json.loads(paths.dlc_load.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    enabled = list(data.get("enabled_mods") or [])
    if registry not in enabled:
        enabled.append(registry)
        data["enabled_mods"] = enabled
        paths.dlc_load.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_playset_backup(paths: GamePaths, playset: Playset, display_name: str) -> None:
    backup = paths.playsets_backup / f"{playset.id}.json"
    if not backup.is_file():
        return
    try:
        data = json.loads(backup.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    mods = list(data.get("mods") or [])
    for item in mods:
        if item.get("displayName") == display_name:
            item["enabled"] = True
            item["position"] = len(mods) - 1
            backup.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            return
    mods.append({"displayName": display_name, "enabled": True, "position": len(mods)})
    data["mods"] = mods
    backup.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
