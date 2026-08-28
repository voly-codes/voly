from __future__ import annotations

from datetime import datetime, timezone

from click.testing import CliRunner

from voly.cli.main import main
from voly.config._parser import _parse_config
from voly.sensing.connectors.rss import RSSConnector
from voly.sensing.store import SignalStore


RSS_FIXTURE = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Market</title>
  <item><title>Competitor cuts pricing</title><guid>entry-42</guid>
  <pubDate>Thu, 27 Aug 2026 10:00:00 GMT</pubDate>
  <description>Enterprise pricing is down 15%.</description></item>
</channel></rss>
"""


def _connector() -> RSSConnector:
    return RSSConnector(
        ["https://example.com/feed.xml"],
        fetch=lambda _url, _timeout: RSS_FIXTURE,
        now=lambda: datetime(2026, 8, 27, 10, 3, tzinfo=timezone.utc),
    )


def test_rss_poll_and_store_deduplicate(tmp_path) -> None:
    store = SignalStore(str(tmp_path / "signals"))
    first = store.save_many(_connector().poll())
    second = store.save_many(_connector().poll())

    assert len(first) == 1
    assert second == []
    assert store.list() == first
    assert first[0].payload["title"] == "Competitor cuts pricing"
    assert (tmp_path / "signals" / "2026-08-27" / f"{first[0].signal_id}.json").exists()


def test_sensing_config_defaults_and_parsing(monkeypatch) -> None:
    monkeypatch.delenv("VOLY_SENSING_ENABLED", raising=False)
    monkeypatch.delenv("VOLY_SENSING_MODE", raising=False)
    assert _parse_config({}).sensing.enabled is False

    config = _parse_config({
        "sensing": {
            "enabled": True,
            "mode": "shadow",
            "store_dir": ".state/signals",
            "connectors": [{"name": "rss", "feeds": ["https://example.com/rss"]}],
        }
    })
    assert config.sensing.enabled is True
    assert config.sensing.connectors[0].name == "rss"
    assert config.sensing.connectors[0].feeds == ["https://example.com/rss"]


def test_cli_poll_fails_closed_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("VOLY_SENSING_ENABLED", raising=False)
    monkeypatch.delenv("VOLY_SENSING_MODE", raising=False)
    result = CliRunner().invoke(main, ["sensing", "poll"])
    assert result.exit_code != 0
    assert "sensing is disabled" in result.output
