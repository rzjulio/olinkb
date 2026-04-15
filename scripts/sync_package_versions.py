from __future__ import annotations

import argparse
import re
from pathlib import Path


def normalize_version(raw_version: str) -> str:
    version = raw_version.strip()
    if version.startswith("v"):
        version = version[1:]
    if not version:
        raise ValueError("Version cannot be empty")
    return version


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, source, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected exactly one match for {path}")
    path.write_text(updated, encoding="utf-8")


def sync_package_versions(repo_root: Path, raw_version: str) -> str:
    version = normalize_version(raw_version)

    replace_once(
        repo_root / "pyproject.toml",
        r'^version = "[^"]+"$',
        f'version = "{version}"',
    )
    replace_once(
        repo_root / "src" / "olinkb" / "__init__.py",
        r'^__version__ = "[^"]+"$',
        f'__version__ = "{version}"',
    )
    replace_once(
        repo_root / "packages" / "olinkb-mcp" / "pyproject.toml",
        r'^version = "[^"]+"$',
        f'version = "{version}"',
    )
    replace_once(
        repo_root / "packages" / "olinkb-mcp" / "pyproject.toml",
        r'^    "olinkb==[^"]+",$',
        f'    "olinkb=={version}",',
    )
    replace_once(
        repo_root / "packages" / "olinkb-mcp" / "src" / "olinkb_mcp" / "__init__.py",
        r'^__version__ = "[^"]+"$',
        f'__version__ = "{version}"',
    )

    return version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize package versions to a release tag version")
    parser.add_argument("version", help="Release version, with or without a leading v")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    version = sync_package_versions(args.repo_root.resolve(), args.version)
    print(f"Synchronized package versions to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())