"""AIGateway skips unhealthy providers after billing errors."""

from __future__ import annotations

from voly.ai_gateway.gateway import AIGateway
from voly.ai_gateway.health import ProviderHealthChecker


def test_gateway_skips_unhealthy_provider_on_chat(monkeypatch) -> None:
    checker = ProviderHealthChecker()
    import voly.ai_gateway.health as health_mod

    monkeypatch.setattr(health_mod, "_checker", checker)
    checker.mark_unhealthy("anthropic", reason="quota_exhausted")

    calls: list[str] = []

    def _fake_direct(self, messages, model, provider_name, *a, **k):
        calls.append(provider_name)
        return {"content": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}

    monkeypatch.setattr(AIGateway, "_delegated_or_direct", _fake_direct)
    monkeypatch.setattr(AIGateway, "_direct_call", _fake_direct)

    gw = AIGateway()
    gw._enabled = True
    gw.account_id = ""  # force non-CF path
    gw.cache.enabled = False

    # Ensure deepseek looks healthy via key presence
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    result = gw.chat(
        [{"role": "user", "content": "hi"}],
        model="claude-sonnet",
        provider_name="anthropic",
    )
    assert not result.get("error"), result
    assert calls
    assert calls[0] != "anthropic"


def test_gateway_marks_billing_error_unhealthy(monkeypatch) -> None:
    checker = ProviderHealthChecker()
    import voly.ai_gateway.health as health_mod

    monkeypatch.setattr(health_mod, "_checker", checker)

    def _fail(self, messages, model, provider_name, *a, **k):
        return {"error": "Your credit balance is too low", "content": ""}

    monkeypatch.setattr(AIGateway, "_delegated_or_direct", _fail)
    monkeypatch.setattr(AIGateway, "_gateway_call", _fail)

    gw = AIGateway()
    gw._enabled = True
    gw.account_id = ""
    gw.cache.enabled = False
    gw.fallback.chain = []
    gw.fallback.retries = 0

    gw.chat([{"role": "user", "content": "hi"}], model="x", provider_name="anthropic")
    assert checker.check("anthropic").healthy is False
