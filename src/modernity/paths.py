"""Workspace layout. The workspace (WS) is the directory containing `BlueMap-GTNH/`; override with `BMGTNH_WORKSPACE`."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]  # tools/modernity
REPO = PROJECT.parents[1]  # BlueMap-GTNH
RENAME_TABLE = PROJECT / "data" / "renames-1.7.10-to-1.13.json"
EXPORTER_LAUNCHER = REPO / "tools" / "gtnh-exporter" / "launcher"

PACK_VERSION = "2.9.0-RC-2"


def workspace() -> Path:
    env = os.environ.get("BMGTNH_WORKSPACE")
    return Path(env) if env else REPO.parent


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
