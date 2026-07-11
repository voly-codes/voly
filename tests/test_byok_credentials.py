"""BYOK (CF AI Gateway Store Keys): credential routing + /compat wiring.

See docs/backend/ai-gateway.md § BYOK (Store Keys).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from voly.ai_gateway import AIGateway
from voly.ai_gateway.credentials import (
    BYOK_PROVIDER_SLUGS,
    byok_active,
    byok_provider_slug,
    gateway_model,
)
from voly.config import VOLYConfig, load_config


def _gw(**kw) -> SimpleNamespace:
    base = {"byok_enabled": True, "account_id": "acct", "api_token": "tok"}
    base.update(kw)
    return SimpleNamespace(**base)


def test_byok_slug_map() -> None:
    assert byok_provider_slug("anthropic") == "anthropic"
    assert byok_provider_slug("google") == "google-ai-studio"
    assert byok_provider_slug("google-ai-studio") == "google-ai-studio"
    assert byok_provider_slug("deepseek") == "deepseek"
    # not proxied by AI Gateway → env path
    assert byok_provider_slug("mimo") == ""
    assert byok_provider_slug("opencode-zen") == ""
    assert byok_provider_slug("omniroute") == ""
    assert byok_provider_slug("workers-ai") == ""


def test_gateway_model_normalizes_anthropic_minor_version() -> None:
    """CF catalog wants claude-sonnet-4.6, Anthropic API ids use hyphens."""
    assert gateway_model("anthropic", "claude-sonnet-4-6") == "claude-sonnet-4.6"
    assert gateway_model("anthropic", "claude-haiku-4-5") == "claude-haiku-4.5"
    # dated ids and non-matching names pass through untouched
    assert gateway_model("anthropic", "claude-haiku-4-5-20251001") == "claude-haiku-4-5-20251001"
    assert gateway_model("anthropic", "claude-x") == "claude-x"
    assert gateway_model("openai", "gpt-4o-mini") == "gpt-4o-mini"
    assert gateway_model("deepseek", "deepseek-chat") == "deepseek-chat"


def test_byok_providers_restriction() -> None:
    assert byok_provider_slug("anthropic", ["anthropic"]) == "anthropic"
    assert byok_provider_slug("openai", ["anthropic"]) == ""
    # restriction list may use the CF slug too
    assert byok_provider_slug("google", ["google-ai-studio"]) == "google-ai-studio"


def test_byok_active_requires_flag_and_creds(monkeypatch) -> None:
    for var in ("CLOUDFLARE_ACCOUNT_ID", "CF_AIG_TOKEN", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert byok_active(_gw()) is True
    assert byok_active(_gw(byok_enabled=False)) is False
    assert byok_active(_gw(account_id="")) is False
    assert byok_active(_gw(api_token="")) is False
    # env can supply the missing pieces
    monkeypatch.setenv("CF_AIG_TOKEN", "aig")
    assert byok_active(_gw(api_token="")) is True


def test_config_byok_defaults() -> None:
    cfg = VOLYConfig()
    assert cfg.ai_gateway.byok_enabled is False
    assert cfg.ai_gateway.byok_providers == []


def test_config_byok_from_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("VOLY_BYOK", raising=False)
    p = tmp_path / "voly.yaml"
    p.write_text(
        "ai_gateway:\n  byok_enabled: true\n  byok_providers:\n    - anthropic\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.ai_gateway.byok_enabled is True
    assert cfg.ai_gateway.byok_providers == ["anthropic"]


def test_config_byok_env_override(tmp_path, monkeypatch) -> None:
    p = tmp_path / "voly.yaml"
    p.write_text("ai_gateway:\n  byok_enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("VOLY_BYOK", "1")
    cfg = load_config(p)
    assert cfg.ai_gateway.byok_enabled is True


def test_direct_call_byok_routes_via_rest_api_without_provider_key(monkeypatch) -> None:
    """BYOK anthropic → CF AI REST API, Bearer account token, no x-api-key."""
    gw = AIGateway(account_id="acct", gateway_id="gw1", api_token="cftok")
    gw.byok_enabled = True
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-leak")
    monkeypatch.delenv("CF_AIG_TOKEN", raising=False)
    monkeypatch.delenv("VOLY_CF_GATEWAY_API", raising=False)

    seen: dict = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data.decode())

        class _Resp:
            def read(self):
                return json.dumps({
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "model": "anthropic/claude-x",
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    import voly.ai_gateway.providers as providers_mod
    monkeypatch.setattr(providers_mod.urllib.request, "urlopen", fake_urlopen)

    out = gw._direct_call([{"role": "user", "content": "hi"}], "claude-x", "anthropic", 100, 0.0, None)
    assert out["content"] == "ok"
    assert seen["url"] == "https://api.cloudflare.com/client/v4/accounts/acct/ai/v1/chat/completions"
    assert seen["body"]["model"] == "anthropic/claude-x"
    hdrs = {k.lower(): v for k, v in seen["headers"].items()}
    assert hdrs.get("authorization") == "Bearer cftok"
    assert hdrs.get("cf-aig-gateway-id") == "gw1"
    # the provider key must never leave the process on the BYOK path
    assert "x-api-key" not in hdrs
    assert "sk-must-not-leak" not in json.dumps(seen["headers"])


def test_direct_call_byok_legacy_compat_escape_hatch(monkeypatch) -> None:
    """VOLY_CF_GATEWAY_API=compat → deprecated gateway host with cf-aig-authorization."""
    gw = AIGateway(account_id="acct", gateway_id="gw1", api_token="cftok")
    gw.byok_enabled = True
    monkeypatch.setenv("VOLY_CF_GATEWAY_API", "compat")
    monkeypatch.delenv("CF_AIG_TOKEN", raising=False)

    seen: dict = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())

        class _Resp:
            def read(self):
                return json.dumps({
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "model": "anthropic/claude-x",
                    "usage": {},
                }).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    import voly.ai_gateway.providers as providers_mod
    monkeypatch.setattr(providers_mod.urllib.request, "urlopen", fake_urlopen)

    out = gw._direct_call([{"role": "user", "content": "hi"}], "claude-x", "anthropic", 100, 0.0, None)
    assert out["content"] == "ok"
    assert seen["url"] == "https://gateway.ai.cloudflare.com/v1/acct/gw1/compat/chat/completions"
    hdrs = {k.lower(): v for k, v in seen["headers"].items()}
    assert hdrs.get("cf-aig-authorization") == "Bearer cftok"
    assert "authorization" not in hdrs


def test_rest_api_requires_cf_token(monkeypatch) -> None:
    """Tokenless direct /compat call (cloudflare-dynamic path) fails fast on REST."""
    gw = AIGateway(account_id="acct", gateway_id="gw1", api_token="")
    for var in ("CLOUDFLARE_API_TOKEN", "CF_AIG_TOKEN", "VOLY_CF_GATEWAY_API"):
        monkeypatch.delenv(var, raising=False)
    out = gw._call_cloudflare_compat(
        "dynamic/ai_route", [{"role": "user", "content": "hi"}], 100, 0.0, None
    )
    assert "CLOUDFLARE_API_TOKEN not set" in out["error"]


def test_direct_call_env_path_unchanged_when_byok_off(monkeypatch) -> None:
    """Flag off → anthropic goes direct with the env key, as before."""
    gw = AIGateway(account_id="acct", gateway_id="gw1", api_token="cftok")
    assert gw.byok_enabled is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    seen: dict = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())

        class _Resp:
            def read(self):
                return json.dumps({
                    "content": [{"type": "text", "text": "ok"}],
                    "model": "claude-x",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    import voly.ai_gateway.providers as providers_mod
    monkeypatch.setattr(providers_mod.urllib.request, "urlopen", fake_urlopen)

    out = gw._direct_call([{"role": "user", "content": "hi"}], "claude-x", "anthropic", 100, 0.0, None)
    assert out["content"] == "ok"
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    hdrs = {k.lower(): v for k, v in seen["headers"].items()}
    assert hdrs.get("x-api-key") == "sk-env"


def test_byok_unsupported_provider_uses_env(monkeypatch) -> None:
    """mimo is not BYOK-eligible → env path even with BYOK on."""
    gw = AIGateway(account_id="acct", gateway_id="gw1", api_token="cftok")
    gw.byok_enabled = True
    monkeypatch.setenv("MIMO_API_KEY", "mimo-key")

    seen: dict = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url

        class _Resp:
            def read(self):
                return json.dumps({
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "model": "m",
                    "usage": {},
                }).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp()

    import voly.ai_gateway.providers as providers_mod
    monkeypatch.setattr(providers_mod.urllib.request, "urlopen", fake_urlopen)

    gw._direct_call([{"role": "user", "content": "hi"}], "m", "mimo", 100, 0.0, None)
    assert "gateway.ai.cloudflare.com" not in seen["url"]


def test_gateway_from_config_and_to_dict() -> None:
    gw = AIGateway(account_id="acct")
    gw.from_config({"byok_enabled": True, "byok_providers": ["anthropic"]})
    assert gw.byok_enabled is True
    assert gw.byok_providers == ["anthropic"]
    assert gw.to_dict()["byok"] is True


def test_slug_map_has_no_executor_or_unsupported_entries() -> None:
    for name in ("mimo", "opencode", "opencode-zen", "omniroute", "workers-ai", "cloudflare-dynamic"):
        assert name not in BYOK_PROVIDER_SLUGS


def test_health_checker_byok_provider_healthy_without_env_key(monkeypatch) -> None:
    """PR2: BYOK-covered provider is healthy with no env key (a2a tier resolution)."""
    from voly.ai_gateway.health import ProviderHealthChecker

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CF_AIG_TOKEN", "aig")

    checker = ProviderHealthChecker()
    assert checker.check("anthropic").healthy is False  # BYOK off

    checker.configure_byok(True)
    st = checker.check("anthropic")
    assert st.healthy is True
    assert "byok" in st.reason
    # non-BYOK provider still needs its env key
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    assert checker.check("mimo").healthy is False


def test_health_checker_byok_respects_restriction_and_env_default(monkeypatch) -> None:
    from voly.ai_gateway.health import ProviderHealthChecker

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CF_AIG_TOKEN", "aig")

    checker = ProviderHealthChecker()
    checker.configure_byok(True, ["anthropic"])
    assert checker.check("anthropic").healthy is True
    assert checker.check("openai").healthy is False

    # VOLY_BYOK env default applies when configure_byok was never called
    env_checker = ProviderHealthChecker()
    monkeypatch.setenv("VOLY_BYOK", "1")
    assert env_checker.check("anthropic").healthy is True


def test_health_checker_byok_needs_cf_creds(monkeypatch) -> None:
    from voly.ai_gateway.health import ProviderHealthChecker

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CF_AIG_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    checker = ProviderHealthChecker()
    checker.configure_byok(True)
    assert checker.check("anthropic").healthy is False


def test_gateway_config_error_not_billing() -> None:
    """PR2: cf-aig / missing provider key ≠ provider billing state."""
    from voly.ai_gateway.error_classifier import (
        ErrorType,
        classify_provider_error,
        is_gateway_config_error,
        is_terminal_billing_error,
    )

    for text in (
        "CF-dynamic 401: invalid cf-aig-authorization header",
        "gateway authentication failed",
        "provider key not found for anthropic (BYOK)",
    ):
        assert is_gateway_config_error(text) is True
        assert classify_provider_error(401, text) == ErrorType.UNAUTHORIZED
        assert is_terminal_billing_error(text, 401) is False

    # a provider billing body relayed through the gateway is still billing
    relayed = "cf-aig gateway: your credit balance is too low"
    assert is_terminal_billing_error(relayed, 400) is True
