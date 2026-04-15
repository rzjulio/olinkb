from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_sync_package_versions_updates_base_and_addon_metadata(tmp_path) -> None:
    (tmp_path / "src" / "olinkb").mkdir(parents=True)
    (tmp_path / "packages" / "olinkb-mcp" / "src" / "olinkb_mcp").mkdir(parents=True)

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "olinkb"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "olinkb" / "__init__.py").write_text(
        '__version__ = "0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "packages" / "olinkb-mcp" / "pyproject.toml").write_text(
        '[project]\nname = "olinkb-mcp"\nversion = "0.1.0"\ndependencies = [\n    "olinkb==0.1.0",\n    "mcp>=1.27.0",\n]\n',
        encoding="utf-8",
    )
    (tmp_path / "packages" / "olinkb-mcp" / "src" / "olinkb_mcp" / "__init__.py").write_text(
        '__version__ = "0.1.0"\n',
        encoding="utf-8",
    )

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "sync_package_versions.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "v0.1.3", "--repo-root", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Synchronized package versions to 0.1.3" in result.stdout
    assert 'version = "0.1.3"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "0.1.3"' in (tmp_path / "src" / "olinkb" / "__init__.py").read_text(encoding="utf-8")

    addon_pyproject = (tmp_path / "packages" / "olinkb-mcp" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.1.3"' in addon_pyproject
    assert '"olinkb==0.1.3",' in addon_pyproject
    assert '__version__ = "0.1.3"' in (
        tmp_path / "packages" / "olinkb-mcp" / "src" / "olinkb_mcp" / "__init__.py"
    ).read_text(encoding="utf-8")