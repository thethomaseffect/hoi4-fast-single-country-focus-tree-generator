# Hearts of Iron 4 - Single Country Focus Tree Generator

## About

This is a tool for Hearts of Iron 4 that allows generating modified versions of focus trees for each individual country in a playset. The console commands available affect all players, making it quite awkward for players who want to complete focuses at their own pace. Generic mods also rely on the same framework and so affect every country in the game.

The thumbnail of any created mods is the country flag overlaid on a 512x512 template (`template_vanilla` by default). This can of course be manually edited later, but reruns of the script will overwrite any changes so be sure to back them up.

This tool analyses a playset and generates an individual mod for every country tailored to the version of the focus tree that will actually be loaded by the game. The advantages of this approach are:

- You don't need complex code to test or cheat faster focuses that only affect a chosen country
- Because the mod understands load order it will always generate a version compatible with the chosen playset, meaning if you alter the mods in the playset just running the tool will update the mods based on the new files. It also will add all mods that affect focus trees as dependencies using the same load order as the playset.
- Any time mods are updated in a way that changes the focus tree, causing a generated mod to overwrite the update, the issue can be resolved by simply re-running the script and, if uploaded to Steam Workshop or Paradox Mods,updating it there.

## Install

```
pip install -r requirements.txt
```

Run from the repository root:

```
python -m src
```

## Instructions for Use

### Easy Mode

If you run the script without any arguments it will create a single mod using the currently selected playset for the selected country in the most recent save file and then add that mod at the bottom of the load order for that playset. This means you can start a new game with your chosen country, save and exit, run the script, then reopen the paradox launcher and play the same with focuses that complete at the start of the next in-game day.

### Complex Mode

The script has two ways of being configured: Command-line arguments and a options.yaml file (recommended for compatibility across platforms). The order of priority are CLI argument, options.yml and finally the defaults of the software. The options available are:

| Option | Description | Default |
| --- | --- | --- |
| `--country-tags` | Comma-separated country tag(s) of the countries you would like to update. Also supports a single country. | Country in the most recent continue-game save |
| `--all-countries` | Creates/Updates mods for every country that has a loaded focus tree. Providing this argument means `--country-tags` is ignored. | Off |
| `--save-game-location` | Overwrite the default save game location for the game. The save game location is only used by quick mode. | `Documents/Paradox Interactive/Hearts of Iron IV/save games` |
| `--playset` | The name of the playset to base the changes on. | Currently selected playset in the launcher |
| `--add-to-playlist` | Will add any created mods to the provided playlist. Beware using this with `--all-countries` because it could be a lot of mods. | Same playset the trees were generated from |
| `--no-add-to-playlist` | Create the local mod files without changing any playset. | Off |
| `--focus-time` | HOI4 focus `cost` (weeks) written to all selected focuses. The default of `0` completes a focus at the start of the next in-game day. | `0` |
| `--thumbnail` | Path to one 512x512 image. That same image is written as `thumbnail.png` for every country tag generated in this run. When set, `--thumbnail-template` and `--country-flag` are ignored. | Off |
| `--thumbnail-template` | Bundled template name or a path to a 512x512 PNG. The in-game flag is overlaid in the blank centre slot. Names: `vanilla` → `template_vanilla` (default), `owb` → `template_owb`. Ignored if `--thumbnail` is set. | `vanilla` |
| `--country-flag` | Path to one 82x52 flag image used for every country tag generated in this run. Ignored if `--thumbnail` is set. | Each country's `gfx/flags` image |

Commented defaults for every option also live in `options.yaml`. YAML keys use underscores (`country_tags`, `focus_time`, ...).

## Guidelines for using this tool

This software is open source and licensed under the MIT licence.

The assets contained in this repository are licensed under the Creative Commons CC0 1.0 Universal licence (Included in ./ASSETS_LICENCE.md). If you add a new asset you are agreeing it will be available under this licence and that you have the legal right to do so.

The creator of the tool humbly requests that you add the following to the description on Steam Workshop and Paradox Mods should you choose to upload your mod:

```
This mod was created using the HOI4 Single Country Focus Tree Generator by [url=https://steamcommunity.com/id/superdmeggs/]DMEggs[/url] available at [url=https://github.com/thethomaseffect/hoi4-fast-single-country-focus-tree-generator]Github[/url].
```

Since an unaltered mod will contain assets from other mods used for the thumbnail please be respectful if a change is requested from the asset owner, or feel free to replace with your own. There is no requirement to add this arbitration to use this mod, it is simply considered courtesy and makes it easy for potential contributors to find the codebase.  

## Collections of mods uploaded based on this tool

[TODO](https://steamcommunity.com)
