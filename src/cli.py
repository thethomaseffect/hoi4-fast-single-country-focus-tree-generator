from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import (
    Options,
    load_yaml_options,
    options_from_yaml,
)
from .generate import generate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src",
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
        help="Override the HOI4 save games directory. Unused when --country-tags or --all-countries is set.",
    )
    parser.add_argument(
        "--playset",
        dest="playset",
        help="Playset name to read load order from. Defaults to the selected playset.",
    )
    parser.add_argument(
        "--add-to-playlist",
        dest="add_to_playlist",
        help=(
            "Playset that should receive the generated mod(s) at the bottom of "
            "the load order. Complex mode does not add anything to a playset "
            "unless you pass this. Beware using it with --all-countries."
        ),
    )
    parser.add_argument(
        "--no-add-to-playlist",
        dest="no_add_to_playlist",
        action="store_true",
        help="Do not add generated mods to a playset (overrides add_to_playlist).",
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
            "Path to one 512x512 image used as thumbnail.png for every country "
            "tag generated in this run. When set, --thumbnail-template and "
            "--country-flag are ignored."
        ),
    )
    parser.add_argument(
        "--thumbnail-template",
        dest="thumbnail_template",
        help=(
            "Bundled template name (vanilla, owb) or a path to a 512x512 PNG. "
            "The country flag is overlaid in the blank centre slot. Ignored if "
            "--thumbnail is set. Default: vanilla."
        ),
    )
    parser.add_argument(
        "--country-flag",
        dest="country_flag",
        help=(
            "Path to one country flag image used for every country tag generated "
            "in this run. Must be a rectangle with HOI4 flag aspect (82:52). "
            "It is scaled to fill the template slot. Ignored if --thumbnail is set."
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
    if args.thumbnail_template:
        merged.thumbnail_template = args.thumbnail_template
    if args.country_flag:
        merged.country_flag = Path(args.country_flag)
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    cli_argv = sys.argv[1:] if argv is None else list(argv)
    args = parser.parse_args(argv)
    try:
        yaml_data: dict = {}
        for search_dir in _yaml_search_dirs():
            yaml_data = load_yaml_options(search_dir)
            if yaml_data:
                break
        options = _cli_overrides(args, options_from_yaml(yaml_data))
        options.easy_mode = len(cli_argv) == 0
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
