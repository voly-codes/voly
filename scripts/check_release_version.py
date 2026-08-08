"""Ensure a release tag matches the version declared in pyproject.toml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomllib


def declared_version(pyproject: Path) -> str:
    with pyproject.open("rb") as stream:
        return str(tomllib.load(stream)["project"]["version"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Release tag, for example v0.1.0")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()

    expected = f"v{declared_version(args.pyproject)}"
    if args.tag != expected:
        print(f"Release tag {args.tag!r} does not match package version {expected!r}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Release tag matches package version: {expected}")


if __name__ == "__main__":
    main()
