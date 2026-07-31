from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from voly.capability.pack_store import PackStore, PackStoreError
from voly.cli.commands.capability_cmd import capability_cmd


def _ecc_fixture(root: Path) -> Path:
    files = {
        "agents/architect.md": "# Architect\n",
        "skills/search-first/SKILL.md": "---\nname: search-first\n---\n",
        "rules/common/security.md": "# Security\n",
        "hooks/hooks.json": "{}\n",
        "mcp-configs/mcp-servers.json": "{}\n",
        "legacy-command-shims/commands/tdd.md": "# TDD\n",
        "package.json": json.dumps(
            {
                "name": "ecc-universal",
                "version": "2.1.0",
                "license": "MIT",
            }
        ),
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_install_is_atomic_and_skips_quarantined_content(tmp_path: Path) -> None:
    source = _ecc_fixture(tmp_path / "ecc")
    unsafe = source / "hooks/hooks.json"
    unsafe.write_text(json.dumps({"command": "rm -rf ./workspace"}), encoding="utf-8")
    store = PackStore(tmp_path / "packs")

    manifest = store.install_ecc(source)

    destination = tmp_path / "packs/ecc-universal"
    assert destination.is_dir()
    assert (destination / "manifest.json").is_file()
    assert (destination / "manifest.sha256").is_file()
    unsafe_component = next(
        item for item in manifest.components if item.source_path == "hooks/hooks.json"
    )
    assert unsafe_component.status == "quarantined"
    assert unsafe_component.staged_path is None
    assert not (destination / "content/hooks/hooks.json").exists()
    assert not list((tmp_path / "packs").glob(".install-*"))


def test_install_refuses_to_overwrite_existing_pack(tmp_path: Path) -> None:
    source = _ecc_fixture(tmp_path / "ecc")
    store = PackStore(tmp_path / "packs")
    store.install_ecc(source)

    with pytest.raises(PackStoreError, match="already exists"):
        store.install_ecc(source)


def test_failed_install_removes_temporary_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _ecc_fixture(tmp_path / "ecc")
    store_root = tmp_path / "packs"
    store = PackStore(store_root)

    def fail_copy(*_args: object, **_kwargs: object) -> None:
        raise OSError("copy failed")

    monkeypatch.setattr("voly.capability.pack_store.shutil.copyfile", fail_copy)

    with pytest.raises(OSError, match="copy failed"):
        store.install_ecc(source)

    assert not (store_root / "ecc-universal").exists()
    assert not list(store_root.glob(".install-*"))


def test_verify_detects_component_and_manifest_tampering(tmp_path: Path) -> None:
    source = _ecc_fixture(tmp_path / "ecc")
    store = PackStore(tmp_path / "packs")
    manifest = store.install_ecc(source)
    staged = next(item for item in manifest.components if item.staged_path)
    staged_path = tmp_path / "packs/ecc-universal" / str(staged.staged_path)
    staged_path.write_text("tampered", encoding="utf-8")

    result = store.verify("ecc-universal")

    assert result.valid is False
    assert any("hash mismatch" in error for error in result.errors)

    checksum = tmp_path / "packs/ecc-universal/manifest.sha256"
    checksum.write_text("0" * 64, encoding="ascii")
    result = store.verify("ecc-universal")
    assert "manifest checksum mismatch" in result.errors


def test_legacy_commands_create_compatibility_aliases(tmp_path: Path) -> None:
    source = _ecc_fixture(tmp_path / "ecc")
    (source / "legacy-command-shims/commands/tdd.md").write_text(
        "Maintained workflow: skills/search-first/SKILL.md",
        encoding="utf-8",
    )

    manifest = PackStore(tmp_path / "packs").install_ecc(source)

    assert any(
        alias.alias == "tdd"
        and alias.target == "skill:search-first"
        and alias.kind == "command"
        for alias in manifest.compatibility_aliases
    )


def test_deprecated_skill_creates_renamed_skill_alias(tmp_path: Path) -> None:
    source = _ecc_fixture(tmp_path / "ecc")
    old_skill = source / "skills/search-old/SKILL.md"
    old_skill.parent.mkdir(parents=True)
    old_skill.write_text(
        "---\nname: search-old\n"
        'description: "[DEPRECATED - use search-first]"\n---\n',
        encoding="utf-8",
    )

    manifest = PackStore(tmp_path / "packs").install_ecc(source)

    assert any(
        alias.alias == "search-old"
        and alias.target == "skill:search-first"
        and alias.kind == "skill"
        for alias in manifest.compatibility_aliases
    )


def test_remove_deletes_only_selected_pack(tmp_path: Path) -> None:
    source = _ecc_fixture(tmp_path / "ecc")
    store = PackStore(tmp_path / "packs")
    store.install_ecc(source)
    unrelated = tmp_path / "packs/unrelated.txt"
    unrelated.write_text("keep", encoding="utf-8")

    store.remove("ecc-universal")

    assert not (tmp_path / "packs/ecc-universal").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"


def test_pack_cli_install_list_show_verify_remove(tmp_path: Path) -> None:
    source = _ecc_fixture(tmp_path / "ecc")
    store = tmp_path / "packs"
    runner = CliRunner()
    prefix = ["pack", "--store", str(store)]

    install = runner.invoke(
        capability_cmd,
        [*prefix, "install", "ecc", "--source", str(source)],
    )
    assert install.exit_code == 0, install.output
    assert "staged ecc-universal" in install.output

    listed = runner.invoke(capability_cmd, [*prefix, "list"])
    assert listed.exit_code == 0
    assert "ecc-universal" in listed.output

    shown = runner.invoke(capability_cmd, [*prefix, "show", "ecc-universal"])
    assert shown.exit_code == 0
    assert json.loads(shown.output)["schema_version"] == 1

    verified = runner.invoke(capability_cmd, [*prefix, "verify", "ecc-universal"])
    assert verified.exit_code == 0, verified.output

    removed = runner.invoke(
        capability_cmd,
        [*prefix, "remove", "ecc-universal", "--yes"],
    )
    assert removed.exit_code == 0
    assert not (store / "ecc-universal").exists()
