"""Hash-verified downloads: Modernity-GTNH GitHub release assets and Mojang client jars."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MODERNITY_REPO = "ModernityGTNH/Modernity-GTNH"
WEEKLY_29_PREFIX = "weekly-2.9.x-"
PACK_ASSET = "Modernity-2.9.x-*.zip"
MYCTMLIB_ASSET = "MyCTMLib-*-29x.jar"
MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def _request(url: str) -> urllib.request.Request:
    headers = {"User-Agent": "bmgtnh-modernity"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def get_json(url: str):
    with urllib.request.urlopen(_request(url), timeout=60) as resp:
        return json.load(resp)


def file_digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, algorithm: str, expected: str) -> Path:
    """Download `url` to `dest` unless it already exists with the expected digest; verify before renaming into place."""
    if dest.is_file() and file_digest(dest, algorithm) == expected:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(_request(url), timeout=300) as resp, part.open("wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    actual = file_digest(part, algorithm)
    if actual != expected:
        part.unlink()
        raise RuntimeError(f"{url}: {algorithm} {actual} != expected {expected}")
    part.replace(dest)
    return dest


@dataclass(frozen=True)
class Release:
    tag: str
    pack: Path
    myctmlib: Path

    @property
    def pack_stem(self) -> str:
        """`Modernity-2.9.x-fa35a3d` for `Modernity-2.9.x-fa35a3d.zip`."""
        return self.pack.name.removesuffix(".zip")


def _pick_release(releases: list[dict], tag: str | None) -> dict:
    if tag:
        for rel in releases:
            if rel["tag_name"] == tag:
                return rel
        raise RuntimeError(f"release {tag} not found in {MODERNITY_REPO}")
    weekly = [r for r in releases if r["tag_name"].startswith(WEEKLY_29_PREFIX) and not r.get("draft")]
    if not weekly:
        raise RuntimeError(f"no {WEEKLY_29_PREFIX}* release in {MODERNITY_REPO}")
    return max(weekly, key=lambda r: r["published_at"])


def _asset(release: dict, pattern: str) -> dict:
    found = [a for a in release["assets"] if fnmatch.fnmatchcase(a["name"], pattern)]
    if len(found) != 1:
        raise RuntimeError(f"{release['tag_name']}: expected one asset {pattern}, found {[a['name'] for a in found]}")
    return found[0]


def fetch_modernity(dest: Path, tag: str | None = None) -> Release:
    """Download the Modernity pack zip and the MyCTMLib jar of the newest 2.9.x weekly release (or `tag`).

    Verifies the sha256 digests GitHub reports for the assets and records them in `dest/release.json`.
    """
    releases = get_json(f"https://api.github.com/repos/{MODERNITY_REPO}/releases?per_page=50")
    rel = _pick_release(releases, tag)
    files = {}
    for key, pattern in (("pack", PACK_ASSET), ("myctmlib", MYCTMLIB_ASSET)):
        asset = _asset(rel, pattern)
        algorithm, _, expected = asset["digest"].partition(":")
        path = download(asset["browser_download_url"], dest / asset["name"], algorithm, expected)
        files[key] = {"name": asset["name"], "size": asset["size"], "digest": asset["digest"], "path": str(path)}
    (dest / "release.json").write_text(json.dumps({
        "repo": MODERNITY_REPO,
        "tag": rel["tag_name"],
        "name": rel["name"],
        "published_at": rel["published_at"],
        "url": rel["html_url"],
        "license": "CC BY-NC-SA 4.0 (do not commit or redistribute commercially)",
        "files": files,
    }, indent=2) + "\n")
    return Release(rel["tag_name"], Path(files["pack"]["path"]), Path(files["myctmlib"]["path"]))


def local_release(dest: Path) -> Release:
    """The release recorded by a previous `fetch_modernity` into `dest`."""
    meta = json.loads((dest / "release.json").read_text())
    return Release(meta["tag"], Path(meta["files"]["pack"]["path"]), Path(meta["files"]["myctmlib"]["path"]))


def minecraft_client_jar(version: str, cache: Path) -> Path:
    """Mojang client jar of `version`, SHA-1 verified, cached as `cache/minecraft-client-<version>.jar`."""
    dest = cache / f"minecraft-client-{version}.jar"
    manifest = get_json(MOJANG_MANIFEST)
    entry = next(v for v in manifest["versions"] if v["id"] == version)
    client = get_json(entry["url"])["downloads"]["client"]
    return download(client["url"], dest, "sha1", client["sha1"])
