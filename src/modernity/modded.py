"""Modded textures: export the GTNH client with Modernity loaded, then measure what Modernity changed."""

from __future__ import annotations

import io
import json
import zipfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

from .keys import icon_of_exported_texture

# Connected-texture metadata in Modernity: the MyCTMLib `myctmlib` section (`method` defaults to `compact`, see
# https://github.com/ABKQPO/MyCTMLib/blob/main/docs/ctm-methods.md). Its 10 `ctm` sections are CTM-mod
# `ctm_version`/`layer`/`extra.light` emissive data for Twilight Forest tower devices, not connections.
CTM_KEY = "myctmlib"


def _mcmeta(raw: bytes) -> dict | None:
    try:
        meta = json.loads(raw.decode("utf-8-sig"))
    except ValueError:
        return None
    return meta if isinstance(meta, dict) else None


def modernity_ctm(modernity_zip: Path) -> dict:
    """Connected textures in the Modernity pack: textures whose `.png.mcmeta` has a `myctmlib` section, and MCPatcher
    CTM `.properties` files under assets/minecraft/mcpatcher/ctm."""
    with zipfile.ZipFile(modernity_zip) as z:
        names = z.namelist()
        textures: set[str] = set()
        methods: Counter[str] = Counter()
        bad = []
        for n in names:
            if not n.endswith(".png.mcmeta"):
                continue
            meta = _mcmeta(z.read(n))
            if meta is None:
                bad.append(n)
            elif isinstance(section := meta.get(CTM_KEY), dict):
                textures.add(n.removesuffix(".mcmeta"))
                methods[section.get("method", "compact")] += 1
        mcpatcher = sorted(n for n in names if n.startswith("assets/minecraft/mcpatcher/ctm/") and n.endswith(".properties"))
    return {"textures": textures, "methods": dict(methods), "mcpatcher_properties": mcpatcher, "unparsable_mcmeta": bad}


def _pixels_equal(a: bytes, b: bytes) -> bool:
    ia, ib = Image.open(io.BytesIO(a)).convert("RGBA"), Image.open(io.BytesIO(b)).convert("RGBA")
    if ia.size != ib.size:
        # the exporter cuts animation strips without a usable .mcmeta to their first frame
        w = ia.size[0]
        if ib.size[0] != w:
            return False
        ia, ib = ia.crop((0, 0, w, w)), ib.crop((0, 0, w, w))
    return ImageChops.difference(ia, ib).getbbox(alpha_only=False) is None


def compare(default_pack: Path, modernity_pack: Path, modernity_zip: Path) -> dict:
    """Texture-by-texture comparison of the default export and the export with Modernity loaded.

    - `overridden`: exported textures whose bytes differ between the two exports;
    - `provided_by_modernity`: exported textures whose 1.7 resource (`assets/<domain>/textures/blocks/<path>.png`)
      Modernity ships; `provided_and_pixel_equal` of those match Modernity's PNG pixel for pixel (first frame);
    - `ctm`: provided textures that Modernity drives with connected textures; the export holds their base tile, so
      `ctm_base_tile_verified` counts the ones equal to Modernity's base PNG.
    """
    ctm = modernity_ctm(modernity_zip)
    with zipfile.ZipFile(default_pack) as d, zipfile.ZipFile(modernity_pack) as m, zipfile.ZipFile(modernity_zip) as src:
        def textures(z: zipfile.ZipFile) -> set[str]:
            return {n for n in z.namelist() if "/textures/" in n and n.endswith(".png")}

        dt, mt, src_names = textures(d), textures(m), set(src.namelist())
        overridden: Counter[str] = Counter()
        provided: Counter[str] = Counter()
        provided_equal = 0
        changed_not_provided = []
        ctm_used, ctm_verified = [], 0
        for path in sorted(dt & mt):
            ns = path.split("/")[1]
            changed = d.read(path) != m.read(path)
            if changed:
                overridden[ns] += 1
            icon = icon_of_exported_texture(path)
            res = f"assets/{icon[0]}/textures/blocks/{icon[1]}.png" if icon else None
            if res in src_names:
                provided[ns] += 1
                equal = _pixels_equal(m.read(path), src.read(res))
                provided_equal += equal
                if res in ctm["textures"]:
                    ctm_used.append(path)
                    ctm_verified += equal
            elif changed:
                changed_not_provided.append(path)
    return {
        "exported_textures": {"default": len(dt), "modernity": len(mt), "both": len(dt & mt),
                              "only_default": sorted(dt - mt), "only_modernity": sorted(mt - dt)},
        "overridden": sum(overridden.values()),
        "overridden_by_namespace": dict(overridden.most_common()),
        "provided_by_modernity": sum(provided.values()),
        "provided_and_pixel_equal": provided_equal,
        "changed_not_provided": changed_not_provided,
        "ctm": {
            "modernity_ctm_textures": len(ctm["textures"]),
            "modernity_ctm_methods": ctm["methods"],
            "modernity_mcpatcher_properties": len(ctm["mcpatcher_properties"]),
            "used_in_export_base_tile": len(ctm_used),
            "base_tile_verified": ctm_verified,
            "used": ctm_used,
        },
        "modernity_unparsable_mcmeta": ctm["unparsable_mcmeta"],
    }
