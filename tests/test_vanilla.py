import io
import json
import zipfile

from PIL import Image

from modernity import vanilla
from modernity.renames import NEW_DIR, OLD_DIR


def png(image: Image.Image) -> bytes:
    return vanilla.png_bytes(image)


def solid(rgba, size=(16, 16)) -> Image.Image:
    return Image.new("RGBA", size, rgba)


def test_rotate_cw_turns_each_animation_frame():
    # two 4x4 frames, each with one marked pixel in the top-left corner
    strip = Image.new("RGBA", (4, 8))
    strip.putpixel((0, 0), (255, 0, 0, 255))
    strip.putpixel((0, 4), (0, 255, 0, 255))
    out = vanilla.rotate_cw(strip)
    assert out.size == (4, 8)
    assert out.getpixel((3, 0)) == (255, 0, 0, 255)  # clockwise: top-left -> top-right
    assert out.getpixel((3, 4)) == (0, 255, 0, 255)  # second frame rotated on its own
    assert out.getpixel((0, 0))[3] == 0


def test_crop_to_box_scales_with_resolution():
    out = vanilla.crop_to_box(solid((200, 0, 0, 255), (32, 32)), (5, 5, 11, 11))
    assert out.getchannel("A").getbbox() == (10, 10, 22, 22)


def test_untint_inverts_the_water_tint():
    tint = bytes.fromhex("3f76e4")
    grey = (177, 177, 177)
    tinted = tuple(round(g * t / 255) for g, t in zip(grey, tint))  # what the game shows
    out = vanilla.untint(solid((*tinted, 180)), "3f76e4").getpixel((0, 0))
    assert all(abs(o - g) <= 2 for o, g in zip(out[:3], grey))
    assert out[3] == 180
    assert vanilla.untint(solid((255, 255, 255, 255)), "3f76e4").getpixel((0, 0)) == (255, 255, 255, 255)


def make_jar_1_13(path):
    dot = Image.new("RGBA", (16, 16))
    for x in range(5, 11):
        for y in range(6, 12):
            dot.putpixel((x, y), (255, 255, 255, 255))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(NEW_DIR + "redstone_dust_dot.png", png(dot))
        for name in ("oak_planks", "redstone_dust_line0", "water_still", "andesite", "stone"):
            z.writestr(NEW_DIR + name + ".png", png(solid((0, 0, 0, 255))))


TABLE = {
    "waterTint": "3f76e4",
    "mapped": {
        "planks_oak": [{"to": "oak_planks", "op": "copy", "via": "rpc"}],
        "redstone_dust_cross": [{"to": "redstone_dust_dot", "op": "redstone_dot", "via": "manual"}],
        "redstone_dust_line": [{"to": "redstone_dust_line0", "op": "rotate_cw", "via": "manual"}],
        "water_still": [{"to": "water_still", "op": "untint", "via": "manual"}],
        "stone": [{"to": "stone", "op": "copy", "via": "identity"}],
    },
    "unmapped": {"leaves_oak_opaque": "fast graphics"},
}


def test_build_maps_renames_ops_animations_and_modern_names(tmp_path):
    jar = tmp_path / "1.13.jar"
    make_jar_1_13(jar)
    planks = png(solid((10, 20, 30, 255)))
    src = tmp_path / "Modernity.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("README.md", "credits")
        z.writestr(OLD_DIR + "planks_oak.png", planks)
        z.writestr(OLD_DIR + "redstone_dust_cross.png", png(solid((90, 90, 90, 255))))
        line = Image.new("RGBA", (16, 16))
        line.paste((90, 90, 90, 255), (0, 7, 16, 9))  # horizontal bar
        z.writestr(OLD_DIR + "redstone_dust_line.png", png(line))
        z.writestr(OLD_DIR + "water_still.png", png(solid((44, 82, 159, 180), (16, 32))))
        z.writestr(OLD_DIR + "water_still.png.mcmeta", '\ufeff{"animation": {"frametime": 2}, "myctmlib": {}}')
        z.writestr(OLD_DIR + "leaves_oak_opaque.png", planks)
        andesite = png(solid((0, 0, 0, 255)))  # modern name that exists in 1.13, same pixels as the vanilla one
        z.writestr(OLD_DIR + "andesite.png", andesite)
        z.writestr(OLD_DIR + "amethyst_block.png", planks)  # modern name that 1.13 does not have
        z.writestr("assets/gregtech/textures/blocks/x.png", planks)  # not vanilla
    out = tmp_path / "out" / "pack.zip"
    report = vanilla.build(src, TABLE, jar, out, "Modernity-test")

    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        assert z.read(NEW_DIR + "oak_planks.png") == planks  # copies are byte-exact
        assert z.read(NEW_DIR + "andesite.png") == andesite
        line0 = Image.open(io.BytesIO(z.read(NEW_DIR + "redstone_dust_line0.png")))
        assert line0.getchannel("A").getbbox() == (7, 0, 9, 16)  # upright
        dot = Image.open(io.BytesIO(z.read(NEW_DIR + "redstone_dust_dot.png")))
        assert dot.getchannel("A").getbbox() == (5, 6, 11, 12)
        water = Image.open(io.BytesIO(z.read(NEW_DIR + "water_still.png"))).convert("RGBA").getpixel((0, 0))
        assert max(water[:3]) - min(water[:3]) <= 3  # grey after removing the tint
        assert json.loads(z.read(NEW_DIR + "water_still.png.mcmeta")) == {"animation": {"frametime": 2}}
        assert json.loads(z.read("pack.mcmeta"))["pack"]["pack_format"] == 4
        assert "LICENSE-NOTICE.txt" in names and z.read("MODERNITY-README.md") == b"credits"
        assert not any("opaque" in n or "amethyst" in n or "gregtech" in n for n in names)

    data = report.to_json()
    assert data["counts"]["mapped_1_7_10_textures"] == 4
    assert data["counts"]["modern_named_identity"] == 1
    assert data["unmapped_1_7_10"] == {"leaves_oak_opaque": "fast graphics"}
    assert data["unmapped_not_1_13_names"] == ["amethyst_block"]
    assert data["vanilla_1_7_10_not_in_pack"] == ["stone"]
    assert data["counts"]["animations"] == 1
    assert data["same_as_1_13_vanilla"] == ["andesite"]
