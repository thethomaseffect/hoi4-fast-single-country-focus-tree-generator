from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import Options
from .game import (
    CountryFocusPlan,
    Playset,
    find_flag_path,
    generated_mod_display_name,
    generated_mod_folder_name,
    latest_save_tag,
    load_playset,
    plan_country_focus,
    register_local_mod,
    remove_local_mod_files,
    resolve_country_names,
    resolve_country_tags,
    resolve_game_files,
    stale_generated_folders,
    unregister_local_mod,
    update_dlc_load,
    update_playset_backup,
)
from .paths import GamePaths, game_supported_version, resolve_paths
from .pdx import (
    focus_trees_in_file,
    parse_pdx_file,
    read_pdx_text,
    rewrite_focus_costs,
    write_descriptor,
)
from .thumbnail import resolve_thumbnail_template, write_custom_thumbnail, write_templated_thumbnail

MOD_TAGS = ["National Focuses", "Utilities"]


@dataclass
class GeneratedMod:
    tag: str
    folder_name: str
    display_name: str
    path: Path
    last_mod_name: str
    files_written: int
    costs_changed: int


def _target_tags(options: Options, paths: GamePaths, playset: Playset) -> list[str]:
    if options.all_countries:
        return resolve_country_tags(paths, playset)
    if options.country_tags:
        return [tag.upper() for tag in options.country_tags]
    tag, _save = latest_save_tag(paths, options.save_game_location)
    return [tag]


def _playlist_target(options: Options, analysis_playset: Playset, paths: GamePaths) -> Playset | None:
    if not options.add_to_playlist_enabled:
        return None
    name = options.add_to_playlist or analysis_playset.name
    if name == analysis_playset.name:
        return analysis_playset
    return load_playset(paths, name)


def _supported_version(paths: GamePaths, plan: CountryFocusPlan) -> str:
    if plan.last_mod and plan.last_mod.required_version:
        return plan.last_mod.required_version
    return game_supported_version(paths)


def _allowed_spans(path: Path, tree_ids: list[str]) -> list[tuple[int, int]]:
    root = parse_pdx_file(path)
    trees = focus_trees_in_file(root)
    if tree_ids:
        return [(tree.start, tree.end) for tree in trees if tree.tree_id in tree_ids]
    return [(tree.start, tree.end) for tree in trees]


def _write_focus_files(plan: CountryFocusPlan, dest_focus_dir: Path, focus_time: float) -> tuple[int, int]:
    dest_focus_dir.mkdir(parents=True, exist_ok=True)
    files_written = 0
    costs_changed = 0
    for loaded in plan.files:
        text = read_pdx_text(loaded.path)
        spans = _allowed_spans(loaded.path, plan.tree_ids)
        rewritten, changed = rewrite_focus_costs(text, focus_time, spans)
        (dest_focus_dir / loaded.relative_name).write_text(rewritten, encoding="utf-8")
        files_written += 1
        costs_changed += changed
    return files_written, costs_changed


def write_country_mod(
    options: Options,
    paths: GamePaths,
    playset: Playset,
    plan: CountryFocusPlan,
    country_name: str,
) -> GeneratedMod:
    folder_name = generated_mod_folder_name(plan.last_mod_name, plan.tag)
    display_name = generated_mod_display_name(country_name)
    for stale in stale_generated_folders(paths, plan.tag, folder_name):
        unregister_local_mod(paths, stale)
        remove_local_mod_files(paths, stale)
    mod_dir = paths.mods / folder_name
    if mod_dir.exists():
        shutil.rmtree(mod_dir)
    mod_dir.mkdir(parents=True, exist_ok=True)

    files_written, costs_changed = _write_focus_files(
        plan, mod_dir / "common" / "national_focus", options.focus_time
    )

    thumbnail_dest = mod_dir / "thumbnail.png"
    if options.thumbnail:
        write_custom_thumbnail(options.thumbnail, thumbnail_dest)
    else:
        if options.country_flag:
            flag = options.country_flag
            require_flag_size = True
        else:
            flag = find_flag_path(paths, playset, plan.tag)
            if flag is None:
                raise FileNotFoundError(f"Could not find a flag for {plan.tag}")
            require_flag_size = False
        write_templated_thumbnail(
            resolve_thumbnail_template(options.thumbnail_template),
            flag,
            thumbnail_dest,
            require_flag_size=require_flag_size,
        )

    supported = _supported_version(paths, plan)
    descriptor = write_descriptor(
        name=display_name,
        tags=MOD_TAGS,
        dependencies=plan.dependencies,
        supported_version=supported,
    )
    (mod_dir / "descriptor.mod").write_text(descriptor, encoding="utf-8")

    mod_path = paths.mods.as_posix() + "/" + folder_name
    registry = write_descriptor(
        name=display_name,
        tags=MOD_TAGS,
        dependencies=plan.dependencies,
        supported_version=supported,
        path=mod_path,
    )
    (paths.mods / f"{folder_name}.mod").write_text(registry, encoding="utf-8")

    return GeneratedMod(
        tag=plan.tag,
        folder_name=folder_name,
        display_name=display_name,
        path=mod_dir,
        last_mod_name=plan.last_mod_name,
        files_written=files_written,
        costs_changed=costs_changed,
    )


def generate(options: Options) -> list[GeneratedMod]:
    paths = resolve_paths(
        documents=options.hoi4_documents,
        mods_directory=options.mods_directory,
        save_game_location=options.save_game_location,
        workshop_content=options.workshop_content,
        hoi4_install=options.hoi4_install,
    )
    paths.mods.mkdir(parents=True, exist_ok=True)
    playset = load_playset(paths, options.playset)
    loaded_focus = resolve_game_files(paths, playset, "common/national_focus")
    tags = _target_tags(options, paths, playset)
    country_names = resolve_country_names(paths, playset)
    playlist = _playlist_target(options, playset, paths)

    created: list[GeneratedMod] = []
    missing: list[str] = []
    for tag in tags:
        plan = plan_country_focus(paths, playset, tag, loaded_focus)
        if plan is None:
            missing.append(tag)
            continue
        generated = write_country_mod(
            options,
            paths,
            playset,
            plan,
            country_names.get(plan.tag, plan.tag),
        )
        if playlist is not None:
            register_local_mod(
                paths,
                playlist,
                generated.folder_name,
                generated.display_name,
                _supported_version(paths, plan),
                generated.path / "thumbnail.png",
            )
            update_dlc_load(paths, generated.folder_name)
            update_playset_backup(paths, playlist, generated.display_name)
        created.append(generated)

    if not created:
        detail = f" Missing trees for: {', '.join(missing)}" if missing else ""
        raise RuntimeError("No focus trees were generated." + detail)
    return created
