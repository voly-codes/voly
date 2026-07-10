"""Priority: LocalPatchApplier — FILE blocks, path jail, summary."""

from __future__ import annotations

from pathlib import Path

import pytest

from voly.executor.patch import LocalPatchApplier, PatchResult


def test_apply_file_block(tmp_path: Path) -> None:
    applier = LocalPatchApplier(str(tmp_path))
    response = """
Here is the file:

### FILE: src/hello.py
```python
print("hi")
```
"""
    result = applier.apply(response)
    assert result.success
    assert len(result.applied) == 1
    assert result.applied[0].path == "src/hello.py"
    assert result.applied[0].created is True
    assert (tmp_path / "src" / "hello.py").read_text() == 'print("hi")\n'


def test_apply_overwrites_existing(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("old\n")
    applier = LocalPatchApplier(str(tmp_path))
    result = applier.apply(
        "### FILE: a.txt\n```\nnew content\n```\n"
    )
    assert result.success
    assert result.applied[0].created is False
    assert (tmp_path / "a.txt").read_text() == "new content\n"


def test_no_blocks_skipped(tmp_path: Path) -> None:
    applier = LocalPatchApplier(str(tmp_path))
    result = applier.apply("just some prose without files")
    assert result.success
    assert result.applied == []
    assert any("no FILE" in s for s in result.skipped)


def test_path_escape_rejected(tmp_path: Path) -> None:
    applier = LocalPatchApplier(str(tmp_path))
    # Attempt to write outside cwd via ..
    result = applier.apply(
        "### FILE: ../../../etc/passwd\n```\nx\n```\n"
    )
    # either error or path resolved under cwd — must not escape
    outside = Path("/etc/passwd")
    # our write path must stay under tmp_path if anything applied
    for f in result.applied:
        full = (tmp_path / f.path).resolve()
        assert str(full).startswith(str(tmp_path.resolve()))
    if result.errors:
        assert any("escape" in e.lower() or "passwd" in e or ".." in e for e in result.errors)


def test_multiple_files(tmp_path: Path) -> None:
    applier = LocalPatchApplier(str(tmp_path))
    response = """
### FILE: a.py
```python
a = 1
```

### FILE: b/c.py
```python
b = 2
```
"""
    result = applier.apply(response)
    assert result.success
    assert {f.path for f in result.applied} == {"a.py", "b/c.py"}
    assert (tmp_path / "a.py").read_text().startswith("a = 1")
    assert (tmp_path / "b" / "c.py").read_text().startswith("b = 2")


def test_summary_string(tmp_path: Path) -> None:
    r = PatchResult()
    assert "no changes" in r.summary()
    applier = LocalPatchApplier(str(tmp_path))
    result = applier.apply("### FILE: x.txt\n```\nhi\n```\n")
    s = result.summary()
    assert "applied" in s
    assert "x.txt" in s


def test_file_markdown_variant(tmp_path: Path) -> None:
    applier = LocalPatchApplier(str(tmp_path))
    result = applier.apply("**File:** foo.ts\n```ts\nexport const x = 1\n```\n")
    assert result.success
    assert any(f.path == "foo.ts" for f in result.applied)
