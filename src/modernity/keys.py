"""Python port of resource-key normalization N (legacy/.../ResourceKeys.kt) and the exporter's texture keys
(tools/gtnh-exporter PackKeys.textureKey), to locate a Modernity texture in an exported pack.
Golden vectors: testing/fixtures/resource-key-vectors.json."""

from __future__ import annotations

LEGACY_MINECRAFT_NAMESPACE = "gtnh_minecraft_1_7"


def _kept(c: str) -> bool:
    return "a" <= c <= "z" or "0" <= c <= "9" or c in "_.-"


def normalize(segment: str) -> str:
    out = []
    for c in segment:
        cp = ord(c)
        if cp < 0x80 and _kept(c):
            out.append(c)
        elif "A" <= c <= "Z":
            out.append("~" + c.lower())
        elif cp <= 0xFF:
            out.append(f"!{cp:02x}")
        else:
            # code points above 0xFFFF: one escape per UTF-16 surrogate, like the Kotlin original
            units = c.encode("utf-16-be")
            out.extend(f"!u{int.from_bytes(units[i:i + 2], 'big'):04x}" for i in range(0, len(units), 2))
    return "".join(out)


def normalize_registry_name(name: str) -> tuple[str, str]:
    domain, colon, value = name.partition(":")
    if not colon:
        return "minecraft", normalize(name)
    return normalize(domain), normalize(value)


def denormalize(segment: str) -> str:
    """Inverse of `normalize` (N is injective)."""
    units: list[int] = []
    i = 0
    while i < len(segment):
        c = segment[i]
        if c == "~":
            units.append(ord(segment[i + 1].upper()))
            i += 2
        elif c == "!" and segment[i + 1] == "u":
            units.append(int(segment[i + 2:i + 6], 16))
            i += 6
        elif c == "!":
            units.append(int(segment[i + 1:i + 3], 16))
            i += 3
        else:
            units.append(ord(c))
            i += 1
    return b"".join(u.to_bytes(2, "big") for u in units).decode("utf-16-be", errors="surrogatepass")


def icon_of_exported_texture(pack_path: str) -> tuple[str, str] | None:
    """`(resource domain, icon path)` of an exported `assets/<ns>/textures/block/<path>.png`, i.e. where the 1.7
    client (and a resource pack) keeps it: `assets/<domain>/textures/blocks/<icon path>.png`. 1.7 resource
    domains are lower case."""
    parts = pack_path.split("/")
    if len(parts) < 5 or parts[0] != "assets" or parts[2:4] != ["textures", "block"] or not pack_path.endswith(".png"):
        return None
    namespace = parts[1]
    domain = "minecraft" if namespace == LEGACY_MINECRAFT_NAMESPACE else denormalize(namespace).lower()
    path = "/".join(denormalize(s) for s in parts[4:])[:-4]
    return domain, path
