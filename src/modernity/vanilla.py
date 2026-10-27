"""Modernity's 1.7.10 vanilla block textures -> a BlueMap resource pack in the 1.13 layout."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops

from .renames import NEW_DIR, OLD_DIR

PACK_FORMAT_1_13 = 4
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"


def frames(image: Image.Image) -> list[Image.Image]:
    """Square animation frames stacked vertically (one frame for a still texture)."""
    w, h = image.size
    if h > w and h % w == 0:
        return [image.crop((0, i * w, w, (i + 1) * w)) for i in range(h // w)]
    return [image]


def stack(parts: list[Image.Image]) -> Image.Image:
    w, h = parts[0].size
    out = Image.new("RGBA", (w, h * len(parts)))
    for i, part in enumerate(parts):
        out.paste(part, (0, i * h))
    return out


def rotate_cw(image: Image.Image) -> Image.Image:
    return stack([f.transpose(Image.Transpose.ROTATE_270) for f in frames(image)])


def crop_to_box(image: Image.Image, box16: tuple[int, int, int, int]) -> Image.Image:
    """Keep only the pixels inside `box16` (left, top, right, bottom in 16x16 units) of every frame."""
    out = []
    for f in frames(image):
        s = f.size[0] / 16
        box = tuple(round(v * s) for v in box16)
        kept = Image.new("RGBA", f.size)
        kept.paste(f.crop(box), box[:2])
        out.append(kept)
    return stack(out)


def untint(image: Image.Image, tint: str) -> Image.Image:
    """Divide RGB by the tint colour (clamped), so that tint * result reproduces the image."""
    r, g, b, a = image.split()
    channels = []
    for channel, t in zip((r, g, b), bytes.fromhex(tint)):
        channels.append(channel.point(lambda v, t=t: min(255, round(v * 255 / t)) if t else 255))
    return Image.merge("RGBA", (*channels, a))


def png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@dataclass
class Report:
    release: str
    written: dict[str, str] = field(default_factory=dict)  # 1.13 name -> source 1.7.10 / Modernity name
    ops: dict[str, int] = field(default_factory=dict)
    animations: int = 0
    mapped_sources: list[str] = field(default_factory=list)
    modern_named: list[str] = field(default_factory=list)
    shadowed_modern_named: list[str] = field(default_factory=list)
    unmapped_listed: dict[str, str] = field(default_factory=dict)
    unmapped_unknown: list[str] = field(default_factory=list)
    vanilla_not_in_pack: list[str] = field(default_factory=list)
    bad_mcmeta: dict[str, str] = field(default_factory=dict)
    # written 1.13 textures that are pixel-identical to the vanilla 1.13 texture (Modernity reuses modern textures)
    same_as_vanilla: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "release": self.release,
            "counts": {
                "modernity_block_textures": len(self.mapped_sources) + len(self.modern_named)
                + len(self.shadowed_modern_named) + len(self.unmapped_listed) + len(self.unmapped_unknown),
                "mapped_1_7_10_textures": len(self.mapped_sources),
                "modern_named_identity": len(self.modern_named),
                "written_1_13_textures": len(self.written),
                "written_same_as_1_13_vanilla": len(self.same_as_vanilla),
                "unmapped_1_7_10_textures": len(self.unmapped_listed),
                "unmapped_not_1_13_names": len(self.unmapped_unknown),
                "shadowed_modern_named": len(self.shadowed_modern_named),
                "vanilla_1_7_10_not_in_pack": len(self.vanilla_not_in_pack),
                "animations": self.animations,
                "ops": dict(sorted(self.ops.items())),
            },
            "unmapped_1_7_10": self.unmapped_listed,
            "unmapped_not_1_13_names": self.unmapped_unknown,
            "shadowed_modern_named": self.shadowed_modern_named,
            "vanilla_1_7_10_not_in_pack": self.vanilla_not_in_pack,
            "bad_mcmeta": self.bad_mcmeta,
            "same_as_1_13_vanilla": self.same_as_vanilla,
            "written": dict(sorted(self.written.items())),
        }


def _animation(raw: bytes) -> dict | None:
    meta = json.loads(raw.decode("utf-8-sig"))
    anim = meta.get("animation")
    return {"animation": anim} if isinstance(anim, dict) else None


def _same_pixels(a: bytes, b: bytes) -> bool:
    ia, ib = Image.open(io.BytesIO(a)).convert("RGBA"), Image.open(io.BytesIO(b)).convert("RGBA")
    return ia.size == ib.size and ImageChops.difference(ia, ib).getbbox(alpha_only=False) is None


def build(modernity_zip: Path, table: dict, jar_1_13: Path, out_zip: Path, release: str) -> Report:
    """Write the 1.13-layout pack to `out_zip` and return what was mapped.

    Sources are Modernity's `assets/minecraft/textures/blocks/*.png`: 1.7.10 names go through `table`; names that
    already are 1.13 block texture names (Modernity ships modern-named textures for backported blocks) are copied
    unchanged unless a 1.7.10 mapping already wrote that target.
    """
    report = Report(release)
    with zipfile.ZipFile(jar_1_13) as jar:
        vanilla_new = {n[len(NEW_DIR):-4]: jar.read(n) for n in jar.namelist()
                       if n.startswith(NEW_DIR) and n.endswith(".png") and "/" not in n[len(NEW_DIR):]}
    dot = Image.open(io.BytesIO(vanilla_new["redstone_dust_dot"])).convert("RGBA")
    dot_box = dot.getchannel("A").getbbox()
    assert dot.size == (16, 16) and dot_box, "unexpected vanilla redstone_dust_dot.png"

    mapped, unmapped, tint = table["mapped"], table["unmapped"], table["waterTint"]
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_zip.with_name(out_zip.name + ".part")
    with zipfile.ZipFile(modernity_zip) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        names = set(src.namelist())
        sources = sorted(n[len(OLD_DIR):-4] for n in names
                         if n.startswith(OLD_DIR) and n.endswith(".png") and "/" not in n[len(OLD_DIR):])
        all_old = set(mapped) | set(unmapped)
        report.vanilla_not_in_pack = sorted(all_old - set(sources))

        def write(new: str, data: bytes, mcmeta: bytes | None, source: str, op: str) -> None:
            dst.writestr(NEW_DIR + new + ".png", data)
            if mcmeta is not None:
                try:
                    anim = _animation(mcmeta)
                except ValueError as ex:
                    report.bad_mcmeta[source] = str(ex)
                    anim = None
                if anim:
                    dst.writestr(NEW_DIR + new + ".png.mcmeta", json.dumps(anim, indent=2) + "\n")
                    report.animations += 1
            report.written[new] = source
            report.ops[op] = report.ops.get(op, 0) + 1
            if _same_pixels(data, vanilla_new[new]):
                report.same_as_vanilla.append(new)

        modern = []
        for name in sources:
            data = src.read(OLD_DIR + name + ".png")
            mcmeta_name = OLD_DIR + name + ".png.mcmeta"
            mcmeta = src.read(mcmeta_name) if mcmeta_name in names else None
            if name in mapped:
                report.mapped_sources.append(name)
                image = None
                for target in mapped[name]:
                    op = target["op"]
                    if op == "copy":
                        out = data
                    else:
                        image = image or Image.open(io.BytesIO(data)).convert("RGBA")
                        if op == "rotate_cw":
                            out = png_bytes(rotate_cw(image))
                        elif op == "redstone_dot":
                            out = png_bytes(crop_to_box(image, dot_box))
                        elif op == "untint":
                            out = png_bytes(untint(image, tint))
                        else:
                            raise ValueError(f"{name}: unknown op {op}")
                    write(target["to"], out, mcmeta, name, op)
            elif name in unmapped:
                report.unmapped_listed[name] = unmapped[name]
            elif name in vanilla_new:
                modern.append((name, data, mcmeta))
            else:
                report.unmapped_unknown.append(name)
        for name, data, mcmeta in modern:
            if name in report.written:
                report.shadowed_modern_named.append(name)
            else:
                report.modern_named.append(name)
                write(name, data, mcmeta, name, "modern_name")

        dst.writestr("pack.mcmeta", json.dumps({"pack": {
            "pack_format": PACK_FORMAT_1_13,
            "description": f"{release} vanilla block textures, 1.7.10 names converted to 1.13 for BlueMap",
        }}, indent=2) + "\n")
        if "README.md" in names:
            dst.writestr("MODERNITY-README.md", src.read("README.md"))
        dst.writestr("LICENSE-NOTICE.txt", (
            f"Textures from Modernity-GTNH ({release}), https://github.com/ModernityGTNH/Modernity-GTNH,\n"
            f"licensed CC BY-NC-SA 4.0 ({LICENSE_URL}); see MODERNITY-README.md for its credits.\n"
            "Changes: renamed from the Minecraft 1.7.10 to the 1.13 texture layout by BlueMap-GTNH tools/modernity;\n"
            "redstone dust dot/line textures cropped and rotated, water textures divided by the default water tint.\n"
            "This derived pack is under the same licence: non-commercial use only, share alike.\n"))
    tmp.replace(out_zip)
    return report
