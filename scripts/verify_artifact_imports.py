#!/usr/bin/env python3
"""Verify a packaged OpenAver artifact can import every bundled top-level package.

Runs ON the artifact's OWN interpreter (Windows embedded ``python.exe`` /
macOS ``python/bin/python3``), so it MUST be stdlib-only and layout-agnostic
(Windows ``Lib/site-packages`` vs macOS ``lib/pythonX.Y/site-packages``).

Why this guard exists (spec-97 G-2):
    ``build.py``/``build_macos.py`` used to strip every ``*.dist-info`` to save
    ~0.5 MB. ``curl_cffi.__init__`` reads its own metadata at import time
    (``importlib.metadata.metadata("curl_cffi")``); with dist-info gone that
    raised ``PackageNotFoundError`` (an ``ImportError`` subclass), which
    ``core/scrapers/javdb.py`` swallowed via ``except ImportError`` — silently
    disabling javdb in EVERY released Windows/macOS build. Dev-venv tests never
    caught it because the venv keeps its dist-info. This sweep imports every
    bundled package using the SHIPPED interpreter, so such breakage fails the
    build (wired into CI as a release gate — see build.yml verify jobs).

Usage:
    <artifact>/python/python.exe scripts/verify_artifact_imports.py [--skip pkg ...]

Exit codes:
    0 — every discovered top-level package imported cleanly.
    1 — at least one import failed (list printed), OR no site-packages was found
        on sys.path (guards against a false-green run on the wrong interpreter).
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

# Directory / file names that are not importable top-level packages.
_SKIP_DIRS = {"__pycache__", "bin", "Scripts"}
_SKIP_SUFFIXES = (".dist-info", ".data")
_EXT_SUFFIXES = (".pyd", ".so")


def _site_packages_dirs() -> list[Path]:
    """Return every ``site-packages`` directory on this interpreter's sys.path.

    Layout-agnostic: we do not hardcode ``Lib/`` vs ``lib/pythonX.Y/`` — we trust
    the shipped interpreter's own resolved sys.path (the artifact ``._pth`` /
    site config puts its site-packages there).
    """
    seen: set[Path] = set()
    dirs: list[Path] = []
    for entry in sys.path:
        if not entry:
            continue
        p = Path(entry)
        if p.name == "site-packages" and p.is_dir():
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                dirs.append(p)
    return dirs


def _top_level_modules(sp_dir: Path) -> tuple[list[str], list[str]]:
    """Collect importable top-level module names inside one site-packages dir.

    Returns (names, skipped) where ``skipped`` lists non-identifier entries
    (namespace dirs, hyphenated names) recorded for transparency.
    """
    names: set[str] = set()
    skipped: list[str] = []
    for entry in sorted(sp_dir.iterdir()):
        name = entry.name
        if name in _SKIP_DIRS or name.endswith(_SKIP_SUFFIXES):
            continue
        if entry.is_dir():
            if (entry / "__init__.py").is_file():
                mod = name
            else:
                continue  # namespace pkg / data dir — not counted
        elif name.endswith(_EXT_SUFFIXES):
            mod = name.split(".")[0]  # _cffi_backend.cp312-win_amd64.pyd -> _cffi_backend
        elif name.endswith(".py"):
            if name == "__init__.py":
                continue
            mod = entry.stem
        else:
            continue
        if not mod.isidentifier():
            skipped.append(name)
            continue
        names.add(mod)
    return sorted(names), skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import every bundled top-level package using the artifact's own interpreter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="PKG",
        help="Top-level module name to skip (repeatable). Use only for a "
        "documented platform-specific special case; prints a SKIP line.",
    )
    args = parser.parse_args(argv)
    skip = set(args.skip)

    print(f"[INFO] interpreter: {sys.executable}")
    sp_dirs = _site_packages_dirs()
    if not sp_dirs:
        print(
            "[FAIL] no site-packages directory found on sys.path — "
            "is this the artifact's own interpreter? (false-green guard)",
            file=sys.stderr,
        )
        return 1

    modules: set[str] = set()
    for sp in sp_dirs:
        print(f"[INFO] site-packages: {sp}")
        names, skipped = _top_level_modules(sp)
        modules.update(names)
        for s in skipped:
            print(f"SKIP  {s} (not an import name)")

    fails: list[tuple[str, str, str]] = []
    for mod in sorted(modules):
        if mod in skip:
            print(f"SKIP  {mod} (--skip)")
            continue
        try:
            importlib.import_module(mod)
        except BaseException as exc:  # noqa: BLE001 — a sweep must catch everything
            fails.append((mod, type(exc).__name__, str(exc)))

    scanned = len(modules) - len(skip & modules)
    print(f"TOTAL {scanned} FAILS {len(fails)}")
    for mod, exc_type, msg in fails:
        print(f"FAIL  {mod}: {exc_type}: {msg}")

    if scanned == 0:
        # A real artifact bundles ~50 packages; zero attempted imports means the
        # sweep found a site-packages dir but nothing importable in it (e.g. a
        # build that stripped every package). Never a legitimate GREEN.
        print(
            "[FAIL] 0 packages attempted — site-packages present but empty of "
            "importable modules (false-green guard)",
            file=sys.stderr,
        )
        return 1

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
