"""Workspace layout. The workspace (WS) is the directory containing this repo and its siblings (`gtnh-exporter/`,
`e2e/`, `BlueMap/`, `downloads/`, `out/`); override with `BMGTNH_WORKSPACE`."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]  # src/modernity/paths.py -> src -> modernity repo
RENAME_TABLE = PROJECT / "data" / "renames-1.7.10-to-1.13.json"

PACK_VERSION = "2.9.0-RC-2"


def workspace() -> Path:
    env = os.environ.get("BMGTNH_WORKSPACE")
    return Path(env) if env else PROJECT.parent


def exporter_launcher() -> Path:
    """`gtnh-client` (sibling gtnh-exporter checkout)."""
    return workspace() / "gtnh-exporter" / "launcher"


def e2e_project() -> Path:
    """The e2e screenshot suite (sibling e2e checkout)."""
    return workspace() / "e2e"


def bluemap_repo() -> Path:
    """The BlueMap fork checkout (sibling `BlueMap/`)."""
    return workspace() / "BlueMap"


def downloads() -> Path:
    """Modernity release assets (user-supplied input, never committed)."""
    return workspace() / "downloads" / "modernity"


def mc_jars() -> Path:
    """Mojang client jars used to build and verify the rename table."""
    return workspace() / "downloads" / "mc"


def out() -> Path:
    return workspace() / "out" / "modernity"


def default_exporter_pack() -> Path:
    return workspace() / "out" / "exporter" / f"bluemap-gtnh-resources-{PACK_VERSION}.zip"
