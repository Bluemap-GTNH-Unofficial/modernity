"""The committed rename table against the real Mojang jars (skipped when `uv run modernity table` has not cached them)."""

import json

import pytest

from modernity import paths, renames

JAR_1_7_10 = paths.mc_jars() / "minecraft-client-1.7.10.jar"
JAR_1_13 = paths.mc_jars() / "minecraft-client-1.13.jar"
RPC = paths.mc_jars() / f"rpc-blocks-{renames.RPC_COMMIT[:7]}.json"
needs_jars = pytest.mark.skipif(not (JAR_1_7_10.is_file() and JAR_1_13.is_file()), reason="Mojang jars not cached")

TABLE = renames.load(paths.RENAME_TABLE)


@needs_jars
def test_every_target_exists_in_1_13_jar():
    new = renames.block_textures(JAR_1_13, renames.NEW_DIR)
    missing = [(o, t["to"]) for o, ts in TABLE["mapped"].items() for t in ts if t["to"] not in new]
    assert missing == []


@needs_jars
def test_every_1_7_10_block_texture_is_mapped_or_explained():
    old = renames.block_textures(JAR_1_7_10, renames.OLD_DIR)
    assert len(old) == 349
    assert set(TABLE["mapped"]) | set(TABLE["unmapped"]) == old
    assert not set(TABLE["mapped"]) & set(TABLE["unmapped"])


@needs_jars
@pytest.mark.skipif(not RPC.is_file(), reason="ResourcePackConverter mapping not cached")
def test_committed_table_is_current():
    assert renames.generate(JAR_1_7_10, JAR_1_13, json.loads(RPC.read_text())["1_13"]) == TABLE


def test_known_renames():
    def targets(old):
        return [(t["to"], t["op"]) for t in TABLE["mapped"][old]]

    assert targets("planks_oak") == [("oak_planks", "copy")]
    assert targets("log_oak_top") == [("oak_log_top", "copy")]
    assert targets("grass_side_overlay") == [("grass_block_side_overlay", "copy")]
    assert targets("double_plant_sunflower_front") == [("sunflower_front", "copy")]
    assert targets("tallgrass") == [("grass", "copy")]
    assert targets("trip_wire_source") == [("tripwire_hook", "copy")]
    assert targets("water_still") == [("water_still", "untint")]
    assert [t for t, _ in targets("command_block")] == [
        "command_block_front", "command_block_back", "command_block_side", "command_block_conditional"]


def test_generate_rejects_missing_targets(tmp_path):
    import zipfile

    old = tmp_path / "old.jar"
    new = tmp_path / "new.jar"
    with zipfile.ZipFile(old, "w") as z:
        for name in ["stone", "planks_oak", *renames.MANUAL, *renames.UNMAPPED]:
            z.writestr(f"{renames.OLD_DIR}{name}.png", b"")
    with zipfile.ZipFile(new, "w") as z:
        z.writestr(f"{renames.NEW_DIR}stone.png", b"")
    with pytest.raises(ValueError, match="planks_oak -> oak_planks: not in the 1.13 jar"):
        renames.generate(old, new, {"planks_oak": "oak_planks"})
