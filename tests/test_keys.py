import json

import pytest

from modernity import keys
from modernity.paths import REPO

VECTORS = json.loads((REPO / "testing" / "fixtures" / "resource-key-vectors.json").read_text())["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=[v["input"] for v in VECTORS])
def test_normalize_matches_golden_vectors(vector):
    assert keys.normalize_registry_name(vector["input"]) == (vector["namespace"], vector["value"])


@pytest.mark.parametrize("vector", VECTORS, ids=[v["input"] for v in VECTORS])
def test_denormalize_inverts_normalize(vector):
    domain, _, value = vector["input"].partition(":")
    assert keys.denormalize(vector["namespace"]) == domain
    assert keys.denormalize(vector["value"]) == value


def test_icon_of_exported_texture():
    # paths as written by the exporter (PackKeys.textureKey)
    assert keys.icon_of_exported_texture(
        "assets/gregtech/textures/block/iconsets/~m~a~c~h~i~n~e_~c~o~i~l_~e~l~e~c~t~r~u~m~f~l~u~x.png"
    ) == ("gregtech", "iconsets/MACHINE_COIL_ELECTRUMFLUX")
    assert keys.icon_of_exported_texture("assets/~chisel/textures/block/glasspanedyed/brown-panel-top.png") == (
        "chisel", "glasspanedyed/brown-panel-top")
    assert keys.icon_of_exported_texture("assets/gtnh_minecraft_1_7/textures/block/log_oak_top.png") == (
        "minecraft", "log_oak_top")
    assert keys.icon_of_exported_texture("assets/gregtech/models/block/x.json") is None
