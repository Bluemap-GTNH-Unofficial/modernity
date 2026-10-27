"""1.7.10 `textures/blocks/<old>.png` -> 1.13 `textures/block/<new>.png` rename table.

The table is generated from three sources, later ones winning:

1. identity: the 1.7.10 name also exists in the 1.13 client jar;
2. ResourcePackConverter's `forwards/blocks.json` `1_13` mapping (agentdid127/ResourcePackConverter, MIT, pinned
   commit; its keys are 1.12 texture names, which the 1.7.10 block texture names it covers still use);
3. `MANUAL` below: names ResourcePackConverter lacks or gets wrong, and split/merged textures that need an image
   operation.

Every target is checked against the 1.13 client jar and every 1.7.10 block texture must be either mapped or listed in
`UNMAPPED` with a reason. The result is committed as `data/renames-1.7.10-to-1.13.json`.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import fetch

RPC_COMMIT = "63ba2cd40294be9436a09c22ad49fb9f1b31e1e0"
RPC_URL = (f"https://raw.githubusercontent.com/agentdid127/ResourcePackConverter/{RPC_COMMIT}"
           "/conversions/Forwards/src/main/resources/forwards/blocks.json")
RPC_SHA256 = "f8200fa7876fb7e37ed28e5d159ca6959bd0179acb3f8ed844981b16bed9f7a6"

OLD_DIR = "assets/minecraft/textures/blocks/"
NEW_DIR = "assets/minecraft/textures/block/"

# Default biome water colour (0x3F76E4). 1.7.10 water textures are coloured and drawn untinted outside swamps;
# 1.13 water textures are grey and multiplied by the biome water colour.
WATER_TINT = "3f76e4"

# old name -> list of (new name, op). Ops are implemented in `vanilla.py`.
MANUAL: dict[str, list[tuple[str, str]]] = {
    # ResourcePackConverter maps these to names that do not exist in 1.13 (trip_wire_hook) or not at all.
    "trip_wire": [("tripwire", "copy")],
    "trip_wire_source": [("tripwire_hook", "copy")],
    "farmland_dry": [("farmland", "copy")],
    "mob_spawner": [("spawner", "copy")],
    "portal": [("nether_portal", "copy")],
    "itemframe_background": [("item_frame", "copy")],
    # 1.13 split the command block into front/back/side/conditional faces; 1.7.10 uses one texture for all six.
    "command_block": [("command_block_front", "copy"), ("command_block_back", "copy"),
                      ("command_block_side", "copy"), ("command_block_conditional", "copy")],
    # 1.7.10 draws an unconnected wire with the full cross; 1.13 uses a centre dot plus vertical line textures.
    # The dot is the cross cropped to the bounding box of the vanilla 1.13 dot; the lines are the 1.7.10
    # horizontal line turned upright (clockwise, the orientation that best matches the vanilla line0 mask).
    "redstone_dust_cross": [("redstone_dust_dot", "redstone_dot")],
    "redstone_dust_line": [("redstone_dust_line0", "rotate_cw"), ("redstone_dust_line1", "rotate_cw")],
    "redstone_dust_cross_overlay": [("redstone_dust_overlay", "copy")],
    # Coloured 1.7.10 water -> grey 1.13 water: divide by the default water tint so that BlueMap's tint restores
    # the pack's intended colour in default-coloured biomes.
    "water_still": [("water_still", "untint")],
    "water_flow": [("water_flow", "untint")],
}

UNMAPPED: dict[str, str] = {
    **{f"bed_{part}": "1.13 beds are drawn from the entity texture textures/entity/bed/<colour>.png (64x64 "
                      "model UV layout); there is no block texture to replace"
       for part in ("feet_end", "feet_side", "feet_top", "head_end", "head_side", "head_top")},
    **{f"leaves_{wood}_opaque": "fast-graphics leaves variant; 1.13 only has the cutout leaves texture"
       for wood in ("acacia", "big_oak", "birch", "jungle", "oak", "spruce")},
    "flower_paeonia": "single-block peony (red_flower meta 8) has no 1.13 block; 1.13 only has the double-plant "
                      "peony_top/peony_bottom (mapped from double_plant_paeonia_*)",
    "redstone_dust_line_overlay": "1.13 has one shared redstone_dust_overlay, taken from redstone_dust_cross_overlay",
}


@dataclass(frozen=True)
class Target:
    to: str
    op: str
    via: str


def block_textures(jar: Path, directory: str) -> set[str]:
    with zipfile.ZipFile(jar) as z:
        return {n[len(directory):-4] for n in z.namelist()
                if n.startswith(directory) and n.endswith(".png") and "/" not in n[len(directory):]}


def rpc_mapping(cache: Path) -> dict[str, str]:
    path = fetch.download(RPC_URL, cache / f"rpc-blocks-{RPC_COMMIT[:7]}.json", "sha256", RPC_SHA256)
    return json.loads(path.read_text())["1_13"]


def generate(jar_1_7_10: Path, jar_1_13: Path, rpc: dict[str, str]) -> dict:
    old = block_textures(jar_1_7_10, OLD_DIR)
    new = block_textures(jar_1_13, NEW_DIR)
    mapped: dict[str, list[Target]] = {}
    for name in sorted(old):
        if name in UNMAPPED:
            continue
        if name in MANUAL:
            mapped[name] = [Target(to, op, "manual") for to, op in MANUAL[name]]
        elif name in rpc:
            mapped[name] = [Target(rpc[name], "copy", "rpc")]
        elif name in new:
            mapped[name] = [Target(name, "copy", "identity")]
    errors = [f"{o} -> {t.to}: not in the 1.13 jar" for o, ts in mapped.items() for t in ts if t.to not in new]
    errors += [f"{o}: neither mapped nor in UNMAPPED" for o in sorted(old - mapped.keys() - UNMAPPED.keys())]
    errors += [f"{o}: listed in MANUAL/UNMAPPED but not a 1.7.10 block texture"
               for o in sorted((MANUAL.keys() | UNMAPPED.keys()) - old)]
    targets: dict[str, str] = {}
    for o, ts in mapped.items():
        for t in ts:
            if t.to in targets:
                errors.append(f"{t.to}: target of both {targets[t.to]} and {o}")
            targets[t.to] = o
    if errors:
        raise ValueError("rename table is inconsistent:\n  " + "\n  ".join(errors))
    return {
        "comment": "Generated by `uv run modernity table` (tools/modernity/src/modernity/renames.py); do not edit.",
        "sources": {
            "resourcePackConverter": {"url": RPC_URL, "sha256": RPC_SHA256,
                                      "license": "MIT, Copyright (c) 2024 agentdid127"},
            "minecraft_1_7_10_blocks": len(old),
            "minecraft_1_13_blocks": len(new),
        },
        "waterTint": WATER_TINT,
        "mapped": {o: [{"to": t.to, "op": t.op, "via": t.via} for t in ts] for o, ts in mapped.items()},
        "unmapped": dict(sorted(UNMAPPED.items())),
    }


def write(table: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, indent=2) + "\n")


def load(path: Path) -> dict:
    return json.loads(path.read_text())
