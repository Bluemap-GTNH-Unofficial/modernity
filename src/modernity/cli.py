"""modernity: build the optional Modernity-GTNH BlueMap packs from a user-supplied Modernity release."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from . import fetch, modded, paths, renames, shots, vanilla


def _release(args) -> fetch.Release:
    """The release recorded by `fetch`, or `--pack ZIP` (with a MyCTMLib-*-29x.jar next to it, if any)."""
    if args.pack:
        pack = Path(args.pack)
        jars = sorted(pack.parent.glob(fetch.MYCTMLIB_ASSET))
        return fetch.Release(pack.stem, pack, jars[-1] if jars else pack.parent / fetch.MYCTMLIB_ASSET)
    return fetch.local_release(paths.downloads())


def cmd_fetch(args) -> int:
    rel = fetch.fetch_modernity(paths.downloads(), args.tag)
    print(f"{rel.tag}: {rel.pack} {rel.myctmlib}")
    return 0


def cmd_table(args) -> int:
    jar_old = fetch.minecraft_client_jar("1.7.10", paths.mc_jars())
    jar_new = fetch.minecraft_client_jar("1.13", paths.mc_jars())
    table = renames.generate(jar_old, jar_new, renames.rpc_mapping(paths.mc_jars()))
    if args.check:
        if renames.load(paths.RENAME_TABLE) != table:
            print(f"{paths.RENAME_TABLE} is out of date; run `uv run modernity table`", file=sys.stderr)
            return 1
        print(f"{paths.RENAME_TABLE} is up to date")
        return 0
    renames.write(table, paths.RENAME_TABLE)
    print(f"{paths.RENAME_TABLE}: {len(table['mapped'])} mapped, {len(table['unmapped'])} unmapped")
    return 0


def vanilla_pack_path(out: Path, rel: fetch.Release) -> Path:
    return out / f"{rel.pack_stem.lower()}-vanilla-1.13.zip"


def modded_pack_path(out: Path, rel: fetch.Release) -> Path:
    return out / f"{rel.pack_stem.lower()}-modded-{paths.PACK_VERSION}.zip"


def cmd_vanilla(args) -> int:
    rel = _release(args)
    out = Path(args.out)
    jar_new = fetch.minecraft_client_jar("1.13", paths.mc_jars())
    target = vanilla_pack_path(out, rel)
    started = time.monotonic()
    report = vanilla.build(rel.pack, renames.load(paths.RENAME_TABLE), jar_new, target, rel.pack_stem)
    data = report.to_json()
    (out / "vanilla-report.json").write_text(json.dumps(data, indent=2) + "\n")
    print(f"{target} ({time.monotonic() - started:.1f} s)")
    print(json.dumps(data["counts"], indent=2))
    return 0


def baseline_pack(out: Path) -> Path:
    return out / "export-default" / f"bluemap-gtnh-resources-{paths.PACK_VERSION}.zip"


def cmd_compare(args) -> int:
    rel = _release(args)
    out = Path(args.out)
    modded_pack = Path(args.modded) if args.modded else modded_pack_path(out, rel)
    report = modded.compare(Path(args.default) if args.default else baseline_pack(out), modded_pack, rel.pack)
    (out / "modded-report.json").write_text(json.dumps(report, indent=2) + "\n")
    summary = {k: v for k, v in report.items() if k in ("overridden", "provided_by_modernity", "provided_and_pixel_equal")}
    summary["exported_textures"] = {k: v if isinstance(v, int) else len(v) for k, v in report["exported_textures"].items()}
    summary["changed_not_provided"] = len(report["changed_not_provided"])
    summary["ctm"] = {k: v for k, v in report["ctm"].items() if k != "used"}
    print(json.dumps(summary, indent=2))
    return 0


def export(out: Path, args, resource_packs: list[Path], extra_mods: list[Path], suffix: str | None) -> Path:
    """Run the GTNH client exporter (tools/gtnh-exporter/launcher) and return the exported pack."""
    out = out.resolve()  # gtnh-client runs in its own directory
    cmd = ["uv", "run", "gtnh-client", "export", "--out", str(out)]
    if args.client_dir:
        cmd += ["--client-dir", str(Path(args.client_dir).resolve())]
    if args.mod_jar:
        cmd += ["--mod-jar", str(Path(args.mod_jar).resolve())]
    for dump in args.extra_states_dump:
        cmd += ["--extra-states-dump", str(Path(dump).resolve())]
    for pack in resource_packs:
        cmd += ["--resource-pack", str(pack.resolve())]
    for jar in extra_mods:
        cmd += ["--extra-mod", str(jar.resolve())]
    if suffix:
        cmd += ["--pack-suffix", suffix]
    print("[modded] " + " ".join(cmd), flush=True)
    code = subprocess.run(cmd, cwd=paths.EXPORTER_LAUNCHER).returncode
    if code != 0:
        raise SystemExit(f"exporter failed with exit code {code}")
    return out / (f"bluemap-gtnh-resources-{paths.PACK_VERSION}" + (f"-{suffix}" if suffix else "") + ".zip")


def cmd_modded(args) -> int:
    rel = _release(args)
    out = Path(args.out)
    if args.baseline:
        # same exporter jar, client and extra states without Modernity: the fair default for `compare` and `e2e`
        export(out / "export-default", args, [], [], None)
    extra_mods = []
    if not args.no_myctmlib:
        # The release requires MyCTMLib; with it the client also uses Modernity's MyCTMLib JSON models (AE2), and
        # fewer GregTech blocks are captured with an Angelica MCPatcher CTM tile instead of their base icon.
        if not rel.myctmlib.is_file():
            raise SystemExit(f"MyCTMLib jar {rel.myctmlib} missing")
        extra_mods.append(rel.myctmlib)
    exported = export(out / "export-modernity", args, [rel.pack], extra_mods, "modernity")
    # Named so that it sorts after `bluemap-gtnh-resources-*.zip`: BlueMap loads config/packs in reverse file-name
    # order and the first pack that provides a resource wins.
    target = modded_pack_path(out, rel)
    shutil.copy2(exported, target)
    with zipfile.ZipFile(target, "a") as z:
        z.writestr("LICENSE-NOTICE.txt", (
            f"Block textures exported from the GTNH {paths.PACK_VERSION} client with Modernity-GTNH ({rel.pack_stem},\n"
            "https://github.com/ModernityGTNH/Modernity-GTNH) enabled. Modernity-GTNH is licensed CC BY-NC-SA 4.0\n"
            f"({vanilla.LICENSE_URL}); the textures it provides stay under that licence: non-commercial use only,\n"
            "share alike. Textures it does not override come from the mods themselves.\n"))
    print(f"[modded] {target}")
    return 0


def cmd_e2e(args) -> int:
    rel = _release(args)
    out = Path(args.out)
    dest = paths.workspace() / "out" / "e2e-modernity"
    default_pack = Path(args.default) if args.default else baseline_pack(out)
    modernity_packs = [default_pack, modded_pack_path(out, rel), vanilla_pack_path(out, rel)]
    for pack in modernity_packs:
        if not pack.is_file():
            raise SystemExit(f"{pack} missing (run `modernity modded --baseline` and `modernity vanilla` first)")
    # Modernity first and default last, so that WS/out/e2e is left with the default render.
    # e2e exits 1 here because Modernity views differ from the default baselines; the shots are what we need.
    if not args.compare_only:
        shots.run_e2e(args.scenes, modernity_packs, build=args.build)
        shots.keep(args.scenes, dest / "modernity")
        shots.run_e2e(args.scenes, [default_pack], build=False)
        shots.keep(args.scenes, dest / "default")
    result = shots.compare(args.scenes, dest / "default", dest / "modernity", dest / "compare")
    for scene, views in result.items():
        for view, data in views.items():
            print(f"{scene:<14} {view:<24} >{shots.PIXEL_TOLERANCE}: {data['diff_ratio']:6.1%}  "
                  f"any: {data['changed_ratio']:6.1%}  {data['side_by_side']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="modernity", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="download the newest 2.9.x weekly Modernity release + MyCTMLib (sha256 verified)")
    p.add_argument("--tag", help="release tag, e.g. weekly-2.9.x-2026-10-26 (default: newest weekly-2.9.x-*)")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("table", help="regenerate data/renames-1.7.10-to-1.13.json from the Mojang jars")
    p.add_argument("--check", action="store_true", help="only verify that the committed table is current")
    p.set_defaults(func=cmd_table)

    def release_args(p):
        p.add_argument("--pack", help="Modernity zip (default: the one recorded by `fetch`)")
        p.add_argument("--out", default=str(paths.out()), help="output directory (default: WS/out/modernity)")

    p = sub.add_parser("vanilla", help="convert Modernity's 1.7.10 vanilla block textures to a 1.13-layout pack")
    release_args(p)
    p.set_defaults(func=cmd_vanilla)

    p = sub.add_parser("compare", help="count what Modernity changed between the default and the Modernity export")
    release_args(p)
    p.add_argument("--default", help="default exporter pack (default: <out>/export-default/... from `modded --baseline`)")
    p.add_argument("--modded", help="Modernity exporter pack (default: <out>/<release>-modded-<pack version>.zip)")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("modded", help="run the GTNH client exporter with the Modernity pack enabled")
    release_args(p)
    p.add_argument("--no-myctmlib", action="store_true", help="do not load the release's MyCTMLib jar in the client")
    p.add_argument("--baseline", action="store_true",
                   help="first export without Modernity into <out>/export-default (same jar, client, extra states)")
    p.add_argument("--client-dir", help="client directory for gtnh-client (default: its default)")
    p.add_argument("--mod-jar", help="exporter mod jar (default: gtnh-client builds it)")
    p.add_argument("--extra-states-dump", action="append", default=[], metavar="DUMP",
                   help="bmh dump.ndjson passed to gtnh-client export; repeatable")
    p.set_defaults(func=cmd_modded)

    p = sub.add_parser("e2e", help="default vs Modernity screenshots via testing/e2e into WS/out/e2e-modernity")
    release_args(p)
    p.add_argument("scenes", nargs="+")
    p.add_argument("--default", help="default exporter pack (default: <out>/export-default/... from `modded --baseline`)")
    p.add_argument("--build", action="store_true", help="let e2e rebuild the CLI/addon jars (default: --no-build)")
    p.add_argument("--compare-only", action="store_true", help="only recompare the kept shots in WS/out/e2e-modernity")
    p.set_defaults(func=cmd_e2e)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
