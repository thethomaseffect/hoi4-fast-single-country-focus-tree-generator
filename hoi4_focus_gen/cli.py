from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hoi4_focus_gen.config import (
    Options,
    load_yaml_options,
    options_from_yaml,
)
from hoi4_focus_gen.generate import generate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hoi4_focus_gen",
        description=(
            "Generate a local HOI4 mod that rewrites one country's focus tree "
            "to the version actually loaded by the selected playset."
        ),
    )
    parser.add_argument(
        "--country-tags",
        dest="country_tags",
        help="Comma-separated country tag(s) to generate mods for.",
    )
    parser.add_argument(
        "--all-countries",
        dest="all_countries",
        action="store_true",
        help="Generate a mod for every country that has a loaded focus tree.",
    )
    parser.add_argument(
        "--save-game-location",
        dest="save_game_location",
        help="Override the HOI4 save games directory (easy mode only).",
    )
    parser.add_argument(
        "--playset",
        dest="playset",
        help="Playset name to read load order from. Defaults to the selected playset.",
    )
    parser.add_argument(
        "--add-to-playlist",
        dest="add_to_playlist",
        help="Playset that should receive the generated mod(s) at the bottom of the load order.",
    )
    parser.add_argument(
        "--no-add-to-playlist",
        dest="no_add_to_playlist",
        action="store_true",
        help="Create the local mod files without changing any playset.",
    )
    parser.add_argument(
        "--focus-time",
        dest="focus_time",
        type=float,
        help="HOI4 focus cost (weeks) to write. Default is 0 (completes at the start of the next in-game day).",
    )
    parser.add_argument(
        "--thumbnail",
        dest="thumbnail",
        help=(
            "Path to one image file used as thumbnail.png for every country "
            "tag generated in this run. Omit to use each country's flag."
        ),
    )
    return parser


def _yaml_search_dirs() -> list[Path]:
    return [Path.cwd(), Path(__file__).resolve().parent.parent]


def _cli_overrides(args: argparse.Namespace, yaml_opts: Options) -> Options:
    """Apply only the CLI values that were actually passed."""
    merged = yaml_opts
    if args.country_tags:
        merged.country_tags = [
            part.strip().upper() for part in args.country_tags.split(",") if part.strip()
        ]
    if args.all_countries:
        merged.all_countries = True
    if args.save_game_location:
        merged.save_game_location = Path(args.save_game_location)
    if args.playset:
        merged.playset = args.playset
    if args.add_to_playlist:
        merged.add_to_playlist = args.add_to_playlist
        merged.add_to_playlist_enabled = True
    if args.no_add_to_playlist:
        merged.add_to_playlist_enabled = False
    if args.focus_time is not None:
        merged.focus_time = args.focus_time
    if args.thumbnail:
        merged.thumbnail = Path(args.thumbnail)
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        yaml_data: dict = {}
        for search_dir in _yaml_search_dirs():
            yaml_data = load_yaml_options(search_dir)
            if yaml_data:
                break
        options = _cli_overrides(args, options_from_yaml(yaml_data))
        generated = generate(options)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for item in generated:
        print(
            f"Created {item.display_name} ({item.folder_name}) from "
            f"{item.last_mod_name}: {item.files_written} file(s), "
            f"{item.costs_changed} focus cost(s) updated -> {item.path}"
        )
    return 0
