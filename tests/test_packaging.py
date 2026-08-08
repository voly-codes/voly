from __future__ import annotations

from pathlib import Path

import tomllib


def test_every_python_package_is_in_wheel_manifest() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(config["tool"]["setuptools"]["packages"])
    discovered = {
        init.parent.relative_to(root).as_posix().replace("/", ".")
        for init in (root / "voly").rglob("__init__.py")
    }

    assert discovered <= declared, f"Packages missing from wheel: {sorted(discovered - declared)}"

