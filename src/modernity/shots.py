"""Default vs Modernity screenshots: run the e2e harness (testing/e2e) once per pack set, keep each run's shots, and
compare them view by view."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageChops

from . import paths

E2E_PROJECT = paths.REPO / "testing" / "e2e"
PIXEL_TOLERANCE = 24  # same per-channel threshold as the e2e scenes' tolerance.pixel


def run_e2e(scenes: list[str], packs: list[Path], build: bool) -> int:
    cmd = ["uv", "run", "e2e", "run", *scenes]
    if not build:
        cmd.append("--no-build")
    for pack in packs:
        cmd += ["--packs", str(pack)]
    print("[e2e] " + " ".join(cmd), flush=True)
    # exit code 1 is expected: Modernity views differ from the default baselines by design
    return subprocess.run(cmd, cwd=E2E_PROJECT).returncode


def keep(scenes: list[str], dest: Path) -> None:
    """Copy each scene's shots, report and log from WS/out/e2e/<scene> to dest/<scene>."""
    for scene in scenes:
        src = paths.workspace() / "out" / "e2e" / scene
        target = dest / scene
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        shutil.copytree(src / "shots", target / "shots")
        for name in ("report.json", "bluemap.log"):
            shutil.copy2(src / name, target / name)
        listing = sorted((src / "config" / "packs").iterdir(), reverse=True)  # BlueMap priority order
        (target / "packs.txt").write_text("".join(f"{p.name}\t{p.stat().st_size}\n" for p in listing))


def diff_ratio(a: Image.Image, b: Image.Image, tolerance: int = PIXEL_TOLERANCE) -> tuple[float, Image.Image]:
    """Share of pixels differing by more than `tolerance` in some RGB channel, and the binary mask."""
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    mask = None
    for band in diff.split():
        over = band.point(lambda v: 255 if v > tolerance else 0)
        mask = over if mask is None else ImageChops.lighter(mask, over)
    hist = mask.histogram()
    return hist[255] / (a.size[0] * a.size[1]), mask


def compare(scenes: list[str], default_dir: Path, modernity_dir: Path, out: Path) -> dict:
    """Side-by-side `default | modernity | differing pixels` images and per-view diff ratios."""
    result = {}
    for scene in scenes:
        views = {}
        for shot in sorted((default_dir / scene / "shots").glob("*.png")):
            other = modernity_dir / scene / "shots" / shot.name
            a, b = Image.open(shot).convert("RGB"), Image.open(other).convert("RGB")
            ratio, mask = diff_ratio(a, b)
            changed, _ = diff_ratio(a, b, 0)
            w, h = a.size
            side = Image.new("RGB", (w * 3, h))
            side.paste(a, (0, 0))
            side.paste(b, (w, 0))
            red = Image.new("RGB", (w, h), (255, 0, 0))
            side.paste(Image.composite(red, Image.eval(b, lambda v: v // 3), mask), (2 * w, 0))
            target = out / scene / shot.name
            target.parent.mkdir(parents=True, exist_ok=True)
            side.save(target)
            views[shot.stem] = {"diff_ratio": round(ratio, 4), "changed_ratio": round(changed, 4),
                                "side_by_side": str(target), "default": str(shot), "modernity": str(other)}
        result[scene] = views
    (out / "compare.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
