"""CLI ``voly run --json`` must exit non-zero when success is false."""

from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner

from voly.cli.commands.run_cmd import run
from voly.pipeline.types import PipelineStage


def test_pipeline_json_exits_nonzero_on_failure(monkeypatch) -> None:
    class _FakePipeline:
        def __init__(self, *a, **k):
            pass

        def setup_environment(self):
            return None

        def run(self, *a, **k):
            return SimpleNamespace(
                success=False,
                stage=PipelineStage.ERROR,
                duration_ms=12.0,
                route=None,
                response=None,
                error="partial failure",
                event=None,
            )

        def shutdown(self):
            return None

    # ``run`` does ``from voly.pipeline import Pipeline`` inside the body.
    import voly.pipeline as pipe_mod

    monkeypatch.setattr(pipe_mod, "Pipeline", _FakePipeline)
    runner = CliRunner()
    result = runner.invoke(
        run,
        ["broken task", "--json"],
        obj={"config": SimpleNamespace()},
    )
    assert result.exit_code == 1, (result.exit_code, result.output, result.exception)
    compact = result.output.replace(" ", "").lower()
    assert '"success":false' in compact
