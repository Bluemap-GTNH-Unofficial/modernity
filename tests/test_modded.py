import io
import json
import zipfile

from PIL import Image

from modernity import modded


def png(rgba, size=(16, 16)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, rgba).save(buf, "PNG")
    return buf.getvalue()


def test_compare_counts_overrides_and_ctm_base_tiles(tmp_path):
    red, blue, green = png((255, 0, 0, 255)), png((0, 0, 255, 255)), png((0, 255, 0, 255))
    coil = "assets/gregtech/textures/block/iconsets/~m~a~c~h~i~n~e_~c~o~i~l.png"
    casing = "assets/gregtech/textures/block/iconsets/~c~a~s~i~n~g.png"
    log = "assets/gtnh_minecraft_1_7/textures/block/log_oak.png"
    untouched = "assets/~chisel/textures/block/marble/raw.png"

    default = tmp_path / "default.zip"
    with zipfile.ZipFile(default, "w") as z:
        for path in (coil, casing, log, untouched):
            z.writestr(path, red)
        z.writestr("assets/gregtech/models/block/a.json", "{}")
    mod_export = tmp_path / "modernity-export.zip"
    with zipfile.ZipFile(mod_export, "w") as z:
        z.writestr(coil, blue)
        z.writestr(casing, green)
        z.writestr(log, blue)
        z.writestr(untouched, red)
    modernity = tmp_path / "Modernity.zip"
    with zipfile.ZipFile(modernity, "w") as z:
        z.writestr("assets/gregtech/textures/blocks/iconsets/MACHINE_COIL.png", blue)
        z.writestr("assets/gregtech/textures/blocks/iconsets/MACHINE_COIL.png.mcmeta",
                   json.dumps({"myctmlib": {"connection": "gregtech:iconsets/MACHINE_COIL_ctm"}}))
        z.writestr("assets/gregtech/textures/blocks/iconsets/MACHINE_COIL_ctm.png", png((0, 0, 255, 255), (64, 64)))
        # same alpha, different colour than the export: must not count as pixel-equal
        z.writestr("assets/minecraft/textures/blocks/log_oak.png", png((0, 0, 250, 255)))
        z.writestr("assets/minecraft/mcpatcher/ctm/glass/glass.properties", "method=ctm")
        z.writestr("assets/enderio/textures/blocks/bad.png.mcmeta", "{animation: {}}")
        z.writestr("assets/twilightforest/textures/blocks/towerdev.png.mcmeta",
                   json.dumps({"ctm": {"ctm_version": 1, "layer": "CUTOUT", "extra": {"light": 15}}}))
        z.writestr("assets/gregtech/textures/blocks/iconsets/GLASS.png.mcmeta",
                   json.dumps({"myctmlib": {"connection": "gregtech:iconsets/GLASS_ctm", "method": "full"}}))

    report = modded.compare(default, mod_export, modernity)
    assert report["exported_textures"]["both"] == 4
    assert report["overridden"] == 3
    assert report["overridden_by_namespace"] == {"gregtech": 2, "gtnh_minecraft_1_7": 1}
    assert report["provided_by_modernity"] == 2  # coil + vanilla log used by a modded block
    assert report["provided_and_pixel_equal"] == 1
    assert report["changed_not_provided"] == [casing]
    assert report["ctm"]["modernity_ctm_textures"] == 2
    assert report["ctm"]["modernity_ctm_methods"] == {"compact": 1, "full": 1}
    assert report["ctm"]["modernity_mcpatcher_properties"] == 1
    assert report["ctm"]["used"] == [coil]
    assert report["ctm"]["base_tile_verified"] == 1
    assert report["modernity_unparsable_mcmeta"] == ["assets/enderio/textures/blocks/bad.png.mcmeta"]
