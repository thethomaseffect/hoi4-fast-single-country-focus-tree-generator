# HOI4 Single Country Focus Tree Generator

This repository is a Python CLI that builds **local** Hearts of Iron IV mods. Each generated mod rewrites one country's national focus tree to the version that playset load order will actually load, then sets focus completion time (default: start of the next in-game day).

Run it from the repo root after `pip install -r requirements.txt`:

```
python -m hoi4_focus_gen
```

Config priority is **CLI > options.yaml / options.yml > built-in defaults**. `options.yaml` ships with every default commented out. Use `[replace with username]` in documented example paths, never a hard-coded Windows username.

## What easy mode does

No arguments means:

1. Read the launcher DB and use the playset with `isActive = 1`.
2. Read `continue_game.json`, then the matching save under `save games`, and take that player country tag.
3. Resolve `common/national_focus` through vanilla + that playset (including `replace_path` and same-filename overwrites).
4. Copy only the focus files whose `focus_tree.country` block assigns that tag (`tag` / `original_tag`).
5. Set those trees' `focus` / `shared_focus` / `joint_focus` `cost` values to `0` (completes at the start of the next in-game day).
6. Write a local mod named `{last_focus_mod}_{tag}_focus_tree_edited`.
7. Build `thumbnail.png` as a 512x512 PNG of that country's flag (flag scaled to fit, transparent padding).
8. Put every playset mod that alters national focuses into `dependencies`, in playset order.
9. Append the generated mod to the bottom of that playset.

## Windows locations

These are the live HOI4 locations the tool reads. Substitute the current user for examples.

| Role | Path |
| --- | --- |
| HOI4 documents | `C:/Users/[replace with username]/Documents/Paradox Interactive/Hearts of Iron IV` |
| Local mods | `...\Hearts of Iron IV/mod` |
| Save games | `...\Hearts of Iron IV/save games` |
| Continue-game pointer | `...\Hearts of Iron IV/continue_game.json` |
| Launcher DB (live playsets) | `...\Hearts of Iron IV/launcher-v2.sqlite` |
| Playset JSON backups | `...\Hearts of Iron IV/playsets_backup` |
| Enabled-mod list the game reads | `...\Hearts of Iron IV/dlc_load.json` |
| Steam workshop content | `C:/Program Files (x86)/Steam/steamapps/workshop/content/394360` |
| Workshop focus trees | `...\394360/[MOD ID]/common/national_focus` |
| Workshop / vanilla flags | `...\gfx/flags/[TAG].tga` |
| Vanilla install | `C:/Program Files (x86)/Steam/steamapps/common/Hearts of Iron IV` |

Steam libraries are also discovered from `libraryfolders.vdf` so HOI4 or workshop content on another drive still resolves.

Override any of these with YAML keys `hoi4_documents`, `mods_directory`, `save_game_location`, `workshop_content`, `hoi4_install`.

## Playsets and the launcher database

`playsets_backup/*.json` is a snapshot. The source of truth is `launcher-v2.sqlite`.

Important tables:

- `playsets` — `id`, `name`, `isActive`
- `playsets_mods` — `playsetId`, `modId`, `enabled`, `position` (load order)
- `mods` — `displayName`, `steamId`, `source` (`steam` / `local`), `dirPath`, `gameRegistryId` (`mod/ugc_[id].mod` or `mod/[folder].mod`), `requiredVersion`

Only **enabled** playset mods are used. Disabled rows are ignored.

Mods produced by this tool (`displayName` ending in `Focus Tree Edited`, folder ending in `_focus_tree_edited`) are skipped when resolving last-editor, source files, and dependencies so a rerun updates the existing generated mod instead of treating it as a new upstream.

When `--add-to-playlist` is in effect (the default), the tool:

- upserts a `source = local` row in `mods`
- puts the mod at `MAX(position) + 1` in `playsets_mods` (or moves an existing row to the bottom)
- appends `mod/[folder].mod` to `dlc_load.json`
- updates the matching `playsets_backup/[playsetId].json` if it exists

Use `--no-add-to-playlist` to write files only.

## How the last focus-tree editor is chosen

This is per country. A later playset mod that only overwrites CES does not become NCR's last editor.

1. Start from vanilla `common/national_focus` unless a playset mod lists `replace_path="common/national_focus"` (Old World Blues does this).
2. Walk enabled playset mods in `position` order.
3. A `replace_path` for `common/national_focus` clears everything loaded so far.
4. Files in that mod's `common/national_focus` add or replace by **filename**.
5. HOI4 assigns **exactly one** focus tree per country. Score every loaded `focus_tree` the same way the game does:
   - Start from `country = { factor / base }`
   - Add each `modifier.add` whose triggers all pass
   - Known triggers: `tag`, `original_tag`, `is_subject_of`, `OR`, `AND`, `NOT` (none-of)
   - `tag` / `original_tag` are compared to the country tag from the save or `--country-tags`. Do not grep file text or filenames for the tag.
   - `is_subject_of` is false unless an overlord is known, so puppet / takeover trees lose for an independent country
   - Unknown scripted triggers do not match
6. Keep only the highest-scoring tree. On a tie, the later file in load order wins. If every score is 0, use the last `default = yes` tree.
7. The last editor is the playset mod that supplied that one winning file (`vanilla` if nothing overwrote it).

`--all-countries` repeats this once per tag in the resolved `common/country_tags` files. Each tag still gets a single tree.

## Generated local mod conventions

Follow the existing local-mod layout (`owb_cmc_ui_fix` style):

```
Documents/Paradox Interactive/Hearts of Iron IV/mod/
  [slug].mod
  [slug]/
    descriptor.mod
    thumbnail.png
    common/national_focus/<original filename(s)>
```

Naming:

- Folder and `.mod` file: `{last_mod_slug}_{country_tag}_focus_tree_edited`
- `last_mod_slug` is the last editor's display name, lowercased, non-alphanumerics turned into underscores
- Example: Old World Blues + NCR → `old_world_blues_ncr_focus_tree_edited`
- `descriptor.mod` `name`: `{TAG} Focus Tree Edited` (example: `NCR Focus Tree Edited`)
- Country tag is part of the folder name so `--all-countries` cannot collide when several countries share the same last editor

`descriptor.mod` has no `path`. The sibling `[slug].mod` file sets `path` with forward slashes, matching other local mods.

Do **not** set `replace_path="common/national_focus"` on generated mods. That would wipe every other country's tree. Overwrite only the copied filenames.

Dependencies are the display names of every playset mod that has a `common/national_focus` folder or `replace_path` for it, in playset order. That is every focus-altering mod that must load before this one.

`supported_version` comes from the last editor's `requiredVersion` / `supported_version`, then falls back to vanilla `launcher-settings.json` `rawVersion`.

Tags written on generated mods: `National Focuses`, `Utilities`.

Reruns delete and recreate the same folder. Back up a hand-edited `thumbnail.png` first.

## Focus cost rules

- `--focus-time` / `focus_time` is the HOI4 `cost` field (weeks). Default `0` completes the focus at the start of the next in-game day.
- Only rewrite `cost` whose immediate parent block is `focus`, `shared_focus`, or `joint_focus`.
- Only rewrite costs inside the single winning `focus_tree` block. Puppet and takeover trees are ignored unless they outscore the unique tree (`is_subject_of` actually matches).

## Flags and thumbnails

Search for the country tag's flag from the end of the playset backwards, then vanilla:

1. `gfx/flags/TAG.tga` (also `.png`)
2. Ideology variants (`TAG_neutrality.tga`, ...)
3. First `gfx/flags/TAG*.tga`

HOI4 flags are typically 82x52 TGA. The thumbnail is always 512x512 PNG. Scale the flag to fit, then pad with a transparent background.

`--thumbnail` is a path to one image file. That single image is used as `thumbnail.png` for every country tag generated in that run. It is not a per-country override: one path, every generated mod. If the option is omitted, each country uses its own flag instead.

## Save-game country detection

Used only when `country_tags` is not set and `all_countries` is false.

1. `continue_game.json` `filename` (example: `NCR_2278_07_02_08.hoi4`)
2. Binary `HOI4bin` saves: first 2–4 letter quoted country token
3. Text `HOI4txt` saves: `player = TAG`
4. Save filename prefix before the first `_`

## Package map

- `hoi4_focus_gen/cli.py` — argparse and YAML merge
- `hoi4_focus_gen/config.py` — options dataclass
- `hoi4_focus_gen/paths.py` — document / Steam / workshop discovery
- `hoi4_focus_gen/pdx.py` — Clausewitz parse, cost rewrite, `.mod` writer
- `hoi4_focus_gen/game.py` — launcher DB, playset, load-order resolve, saves, flags
- `hoi4_focus_gen/thumbnail.py` — 512x512 flag thumbnail
- `hoi4_focus_gen/generate.py` — orchestration and file output

When changing generator behaviour, update this file and the README CLI table together.
