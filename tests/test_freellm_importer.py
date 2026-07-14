"""Tests for voly/catalog/freellm_importer.py.

All tests use in-memory fixtures or tmp_path — no network, no external checkout.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from voly.catalog.fallback import verified_free_fallback
from voly.catalog.freellm_importer import (
    _parse_context_window,
    _parse_rate_limit,
    _parse_auth,
    _parse_modalities,
    _parse_md_table,
    merge_with_catalog,
    parse_readme,
    parse_readme_text,
)
from voly.catalog.types import CatalogModel


# ---------------------------------------------------------------------------
# Minimal fixture README that covers all tested code paths
# ---------------------------------------------------------------------------

FIXTURE_README = """\
<!-- AUTO_UPDATE_BADGE -->
<p>Last updated: 2026-07-14</p>
<!-- END_AUTO_UPDATE_BADGE -->

<!-- AUTO_LAST_UPDATED -->
2026-07-14
<!-- END_AUTO_LAST_UPDATED -->

## Quick Reference

<!-- BEGIN_QUICK_REF -->
| Provider | Base URL | Get API Key | Credit Card? |
|---|---|---|---|
| Groq | `https://api.groq.com/openai/v1` | <a href="https://console.groq.com/keys" target="_blank" rel="noopener">Get Key →</a> | No |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener">Get Key →</a> | No |
| NVIDIA NIM | `https://integrate.api.nvidia.com/v1` | <a href="https://build.nvidia.com/settings/api-keys" target="_blank" rel="noopener">Get Key →</a> | Phone verification |
| ModelScope | `https://api-inference.modelscope.cn/v1` | <a href="https://modelscope.cn/my/myaccesstoken" target="_blank" rel="noopener">Get Key →</a> | Registration |
<!-- END_QUICK_REF -->

## Provider Directory

<!-- BEGIN_PERMANENT_FREE -->
| Provider | Free Models | Credit Card? | Max Context | Modalities | Get API Key |
|---|---|---|---|---|---|
| Groq | 10 | No | 262K | text | <a href="https://console.groq.com/keys" target="_blank" rel="noopener">→</a> |
| Google Gemini | 12 | No | 1M | audio, image, pdf, reasoning, text, video, vision | <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener">→</a> |
| NVIDIA NIM | 117 | Phone verification | 1M | audio, image, reasoning, text, vision | <a href="https://build.nvidia.com/settings/api-keys" target="_blank" rel="noopener">→</a> |
| ModelScope | 54 | Registration | 1M | audio, image, reasoning, text, vision | <a href="https://modelscope.cn/my/myaccesstoken" target="_blank" rel="noopener">→</a> |
<!-- END_PERMANENT_FREE -->

## Best Free Models

<!-- BEGIN_BEST_MODELS -->
| Provider | Best Free Model | Model ID | Max Context | Rate Limit |
|---|---|---|---|---|
| Groq | <a href="https://freellm.net/models/groq/llama-4-maverick/" target="_blank" rel="noopener">llama-4-maverick</a> | `llama-4-maverick-17b-128e-instruct` | 131K | 15 RPM, 500 RPD |
|  | <a href="https://freellm.net/models/groq/llama-3-3-70b/" target="_blank" rel="noopener">Llama 3.3 70B</a> | `llama-3.3-70b-versatile` | 262K | 30 RPM, 14,400 RPD |
| Google Gemini | <a href="https://freellm.net/models/google-gemini/gemini-3-5-flash/" target="_blank" rel="noopener">Gemini 3.5 Flash</a> | `gemini-3.5-flash` | 1M | 15 RPM, 1,500 RPD |
|  | <a href="https://freellm.net/models/google-gemini/gemini-3-1-flash-lite/" target="_blank" rel="noopener">Gemini 3.1 Flash-Lite</a> | `gemini-3.1-flash-lite` | 1M | 30 RPM, 1,500 RPD |
| NVIDIA NIM | <a href="https://freellm.net/models/nvidia-nim/moonshotai-kimi-k2-6/" target="_blank" rel="noopener">moonshotai/kimi-k2.6</a> | `moonshotai/kimi-k2.6` | 262K | Up to 40 RPM |
|  | <a href="https://freellm.net/models/nvidia-nim/z-ai-glm-5-2/" target="_blank" rel="noopener">z-ai/glm-5.2</a> | `z-ai/glm-5.2` | 1M | Up to 40 RPM |
| ModelScope | <a href="https://freellm.net/models/modelscope/minimax-minimax-m2-5/" target="_blank" rel="noopener">MiniMax-M2.5-highspeed</a> | `MiniMax/MiniMax-M2.5` | 204K | 2,000 RPD total; <=500 .. |
<!-- END_BEST_MODELS -->
"""

FIXTURE_README_MALFORMED = """\
<!-- AUTO_LAST_UPDATED -->
2026-07-01
<!-- END_AUTO_LAST_UPDATED -->

<!-- BEGIN_QUICK_REF -->
| Provider | Base URL | Get API Key | Credit Card? |
|---|---|---|---|
| Groq | `https://api.groq.com/openai/v1` | <a href="https://console.groq.com/keys">Get Key →</a> | No |
<!-- END_QUICK_REF -->

<!-- BEGIN_BEST_MODELS -->
| Provider | Best Free Model | Model ID | Max Context | Rate Limit |
|---|---|---|---|---|
| Groq | <a href="https://freellm.net/models/groq/llama-4/">good-model</a> | `good-model` | 131K | 30 RPM |
|  | <a href="">carry-forward</a> | `carry-forward-model` | 64K | |
| | <a href="">missing-provider</a> | | | |
| BadRow | no backtick here | still-an-id | 32K | See provider |
| ExtraColumns | <a href="">model</a> | `extra-col-model` | 64K | 5 RPM | unexpected | extra |
<!-- END_BEST_MODELS -->
"""

FIXTURE_README_COLLISION = """\
<!-- BEGIN_BEST_MODELS -->
| Provider | Best Free Model | Model ID | Max Context | Rate Limit |
|---|---|---|---|---|
| NVIDIA NIM | Llama via NVIDIA | `meta-llama/Meta-Llama-3.1-70B-Instruct` | 128K | 40 RPM |
| Glhf.chat | Llama via Glhf | `meta-llama/Meta-Llama-3.1-70B-Instruct` | 128K | Unlimited |
<!-- END_BEST_MODELS -->
"""


# ---------------------------------------------------------------------------
# Unit tests — parsing helpers
# ---------------------------------------------------------------------------

class TestParseContextWindow:
    def test_k_suffix(self):
        assert _parse_context_window("131K") == 131_000

    def test_m_suffix(self):
        assert _parse_context_window("1M") == 1_000_000

    def test_zero(self):
        assert _parse_context_window("0") == 0

    def test_empty(self):
        assert _parse_context_window("") == 0

    def test_no_suffix(self):
        assert _parse_context_window("32000") == 32000

    def test_decimal(self):
        assert _parse_context_window("1.5M") == 1_500_000


class TestParseRateLimit:
    def test_rpm_only(self):
        assert _parse_rate_limit("30 RPM") == {"rpm": 30}

    def test_rpm_and_rpd(self):
        result = _parse_rate_limit("15 RPM, 1,500 RPD")
        assert result == {"rpm": 15, "rpd": 1500}

    def test_up_to_prefix(self):
        result = _parse_rate_limit("Up to 40 RPM")
        assert result.get("rpm") == 40

    def test_see_provider(self):
        assert _parse_rate_limit("See provider") == {}

    def test_empty(self):
        assert _parse_rate_limit("") == {}

    def test_raw_fallback(self):
        result = _parse_rate_limit("Community-powered, no hard limit")
        assert "raw" in result

    def test_k_suffix_in_rpd(self):
        result = _parse_rate_limit("30 RPM, 14,400 RPD, 1M TPM")
        assert result["rpm"] == 30
        assert result["rpd"] == 14400
        assert result["tpm"] == 1_000_000

    def test_anonymous_parenthetical(self):
        result = _parse_rate_limit("2 RPM (anonymous)")
        assert result.get("rpm") == 2

    def test_partial_truncated_string(self):
        # Truncated strings from the README ("2,000 RPD total; <=500 ..") — store raw
        result = _parse_rate_limit("2,000 RPD total; <=500 ..")
        # RPD is present but there's extra context; raw is acceptable too
        assert "rpd" in result or "raw" in result


class TestParseAuth:
    def test_no(self):
        assert _parse_auth("No") == "none"

    def test_registration(self):
        assert _parse_auth("Registration") == "email"

    def test_phone_verification(self):
        assert _parse_auth("Phone verification") == "phone"

    def test_empty(self):
        assert _parse_auth("") == "none"


class TestParseModalities:
    def test_basic(self):
        assert _parse_modalities("audio, image, text") == ["audio", "image", "text"]

    def test_single(self):
        assert _parse_modalities("text") == ["text"]

    def test_empty(self):
        assert _parse_modalities("") == []


class TestParseMdTable:
    def test_basic_table(self):
        text = """\
| A | B | C |
|---|---|---|
| x | y | z |
| 1 | 2 | 3 |
"""
        header, rows = _parse_md_table(text)
        assert header == ["a", "b", "c"]
        assert len(rows) == 2
        assert rows[0] == ["x", "y", "z"]

    def test_html_in_header(self):
        text = """\
| <b>Provider</b> | URL |
|---|---|
| Groq | https://x |
"""
        header, rows = _parse_md_table(text)
        assert header[0] == "provider"

    def test_empty_input(self):
        header, rows = _parse_md_table("")
        assert header == []
        assert rows == []


# ---------------------------------------------------------------------------
# Integration tests — parse_readme_text
# ---------------------------------------------------------------------------

class TestParseReadmeText:
    def test_model_count(self):
        models = parse_readme_text(FIXTURE_README)
        assert len(models) == 7  # 2 Groq + 2 Gemini + 2 NVIDIA + 1 ModelScope

    def test_provider_carry_forward(self):
        models = parse_readme_text(FIXTURE_README)
        groq_models = [m for m in models if m.provider == "groq"]
        assert len(groq_models) == 2

    def test_base_url_populated(self):
        models = parse_readme_text(FIXTURE_README)
        groq = next(m for m in models if m.provider == "groq")
        assert groq.base_url == "https://api.groq.com/openai/v1"

    def test_rate_limit_structured(self):
        models = parse_readme_text(FIXTURE_README)
        maverick = next(
            m for m in models
            if m.upstream_model_id == "llama-4-maverick-17b-128e-instruct"
        )
        assert maverick.rate_limit.get("rpm") == 15
        assert maverick.rate_limit.get("rpd") == 500

    def test_context_window(self):
        models = parse_readme_text(FIXTURE_README)
        gemini = next(m for m in models if m.upstream_model_id == "gemini-3.5-flash")
        assert gemini.context_window == 1_000_000

    def test_modalities_from_permanent_free(self):
        models = parse_readme_text(FIXTURE_README)
        gemini = next(m for m in models if m.upstream_model_id == "gemini-3.5-flash")
        assert "audio" in gemini.modalities
        assert "text" in gemini.modalities

    def test_auth_requirement(self):
        models = parse_readme_text(FIXTURE_README)
        groq = next(m for m in models if m.provider == "groq")
        assert groq.auth_requirement == "none"
        nvidia = next(m for m in models if m.provider == "nvidia-nim")
        assert nvidia.auth_requirement == "phone"
        modelscope = next(m for m in models if m.provider == "modelscope")
        assert modelscope.auth_requirement == "email"

    def test_source_url_from_link(self):
        models = parse_readme_text(FIXTURE_README)
        maverick = next(
            m for m in models
            if m.upstream_model_id == "llama-4-maverick-17b-128e-instruct"
        )
        assert "freellm.net" in maverick.source_url

    def test_source_updated_at(self):
        models = parse_readme_text(FIXTURE_README)
        assert all(m.source_updated_at == "2026-07-14" for m in models)

    def test_tier_is_free(self):
        models = parse_readme_text(FIXTURE_README)
        assert all(m.tier == "free" for m in models)

    def test_verified_is_false(self):
        models = parse_readme_text(FIXTURE_README)
        assert all(not m.verified for m in models)

    def test_supports_tools_is_none(self):
        models = parse_readme_text(FIXTURE_README)
        assert all(m.supports_tools is None for m in models)

    def test_api_key_url_populated(self):
        models = parse_readme_text(FIXTURE_README)
        groq = next(m for m in models if m.provider == "groq")
        assert "console.groq.com" in groq.api_key_url

    def test_deduplication_idempotent(self):
        # Importing same README twice should produce the same set of model IDs
        models1 = parse_readme_text(FIXTURE_README)
        models2 = parse_readme_text(FIXTURE_README)
        assert {m.id for m in models1} == {m.id for m in models2}

    def test_provider_carry_forward_nvidia(self):
        models = parse_readme_text(FIXTURE_README)
        nvidia_models = [m for m in models if m.provider == "nvidia-nim"]
        assert len(nvidia_models) == 2
        # Both carry-forward rows should have NVIDIA base URL
        for m in nvidia_models:
            assert m.base_url == "https://integrate.api.nvidia.com/v1"

    def test_slash_in_model_id(self):
        """Model IDs with slashes (e.g., moonshotai/kimi-k2.6) are preserved."""
        models = parse_readme_text(FIXTURE_README)
        ids = {m.upstream_model_id for m in models}
        assert "moonshotai/kimi-k2.6" in ids
        assert "MiniMax/MiniMax-M2.5" in ids

    def test_unknown_executor_compatibility_is_empty(self):
        models = parse_readme_text(FIXTURE_README)
        assert all(m.executor_compat == [] for m in models)

    def test_same_upstream_id_from_two_providers_is_preserved(self):
        models = parse_readme_text(FIXTURE_README_COLLISION)
        assert len(models) == 2
        assert {m.upstream_model_id for m in models} == {
            "meta-llama/Meta-Llama-3.1-70B-Instruct"
        }
        assert {m.id for m in models} == {
            "nvidia-nim:meta-llama/Meta-Llama-3.1-70B-Instruct",
            "glhf:meta-llama/Meta-Llama-3.1-70B-Instruct",
        }


class TestMalformedRows:
    def test_malformed_readme_parse_succeeds(self):
        """Parser must not crash on malformed rows."""
        models = parse_readme_text(FIXTURE_README_MALFORMED)
        ids = {m.upstream_model_id for m in models}
        assert "good-model" in ids
        assert "carry-forward-model" in ids

    def test_empty_model_id_falls_back_to_display_name(self):
        models = parse_readme_text(FIXTURE_README_MALFORMED)
        ids = {m.upstream_model_id for m in models}
        # The row has empty model ID column but a display name in the link text.
        # Provider carry-forward gives it "Groq".  Parser falls back to display
        # name ("missing-provider") rather than silently dropping the row.
        assert "missing-provider" in ids

    def test_no_backtick_still_parsed(self):
        models = parse_readme_text(FIXTURE_README_MALFORMED)
        ids = {m.upstream_model_id for m in models}
        # "BadRow" has "still-an-id" in the model ID column without backticks
        assert "still-an-id" in ids

    def test_extra_columns_ignored(self):
        models = parse_readme_text(FIXTURE_README_MALFORMED)
        ids = {m.upstream_model_id for m in models}
        assert "extra-col-model" in ids


# ---------------------------------------------------------------------------
# Tests for missing sections
# ---------------------------------------------------------------------------

FIXTURE_NO_QUICK_REF = """\
<!-- AUTO_LAST_UPDATED -->
2026-07-01
<!-- END_AUTO_LAST_UPDATED -->

<!-- BEGIN_BEST_MODELS -->
| Provider | Best Free Model | Model ID | Max Context | Rate Limit |
|---|---|---|---|---|
| Groq | <a href="https://freellm.net">model</a> | `only-model` | 64K | 5 RPM |
<!-- END_BEST_MODELS -->
"""

def test_missing_quick_ref_still_parses():
    """Models are still produced even without the Quick Reference section."""
    models = parse_readme_text(FIXTURE_NO_QUICK_REF)
    assert len(models) == 1
    assert models[0].id == "groq:only-model"
    assert models[0].upstream_model_id == "only-model"
    assert models[0].base_url == ""  # no provider info available


def test_missing_best_models_raises():
    content = "No sections here."
    with pytest.raises(ValueError, match="No models parsed"):
        parse_readme_text(content)


# ---------------------------------------------------------------------------
# Tests for merge_with_catalog
# ---------------------------------------------------------------------------

class TestMergeWithCatalog:
    def _make_existing(self) -> list[CatalogModel]:
        return [
            CatalogModel(
                id="claude-opus-4-8",
                name="Claude Opus 4.8",
                provider="anthropic",
                tier="premium",
                executor_compat=["zen", "opencode"],
                strengths=["plan", "architecture"],
                enabled=True,
            ),
            CatalogModel(
                id="gemini-3.5-flash",
                name="Gemini 3.5 Flash (zen)",
                provider="google-gemini",
                tier="free",
                executor_compat=["zen"],
                strengths=["fast"],
                enabled=True,
                verified=True,
                last_verified_at="2026-06-01",
            ),
        ]

    def _make_imported(self) -> list[CatalogModel]:
        return [
            CatalogModel(
                id="google-gemini:gemini-3.5-flash",
                upstream_model_id="gemini-3.5-flash",
                name="Gemini 3.5 Flash",
                provider="google-gemini",
                tier="free",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                context_window=1_000_000,
                rate_limit={"rpm": 15, "rpd": 1500},
                auth_requirement="none",
                api_key_url="https://aistudio.google.com/app/apikey",
                source_url="https://freellm.net/models/google-gemini/gemini-3-5-flash/",
                source_updated_at="2026-07-14",
                verified=False,
            ),
            CatalogModel(
                id="groq:llama-4-maverick-17b-128e-instruct",
                upstream_model_id="llama-4-maverick-17b-128e-instruct",
                name="llama-4-maverick",
                provider="groq",
                tier="free",
                base_url="https://api.groq.com/openai/v1",
                context_window=131_000,
                rate_limit={"rpm": 15, "rpd": 500},
                auth_requirement="none",
                verified=False,
            ),
        ]

    def test_non_freellm_models_preserved(self):
        existing = self._make_existing()
        imported = self._make_imported()
        merged = merge_with_catalog(existing, imported)
        ids = {m.id for m in merged}
        assert "claude-opus-4-8" in ids  # non-freellm model preserved

    def test_new_freellm_model_added(self):
        existing = self._make_existing()
        imported = self._make_imported()
        merged = merge_with_catalog(existing, imported)
        ids = {m.id for m in merged}
        assert "groq:llama-4-maverick-17b-128e-instruct" in ids

    def test_routing_fields_preserved_on_conflict(self):
        existing = self._make_existing()
        imported = self._make_imported()
        merged = merge_with_catalog(existing, imported)
        gemini = next(m for m in merged if m.id == "gemini-3.5-flash")
        # Routing fields from existing are preserved
        assert gemini.executor_compat == ["zen"]
        assert gemini.strengths == ["fast"]
        assert gemini.tier == "free"

    def test_metadata_enriched_on_conflict(self):
        existing = self._make_existing()
        imported = self._make_imported()
        merged = merge_with_catalog(existing, imported)
        gemini = next(m for m in merged if m.id == "gemini-3.5-flash")
        # Freellm metadata was added
        assert gemini.base_url == "https://generativelanguage.googleapis.com/v1beta"
        assert gemini.context_window == 1_000_000
        assert gemini.rate_limit == {"rpm": 15, "rpd": 1500}

    def test_verified_flag_preserved_on_conflict(self):
        """Importing must not clear a manually set verified=True."""
        existing = self._make_existing()
        imported = self._make_imported()
        merged = merge_with_catalog(existing, imported)
        gemini = next(m for m in merged if m.id == "gemini-3.5-flash")
        assert gemini.verified is True
        assert gemini.last_verified_at == "2026-06-01"

    def test_idempotent(self):
        existing = self._make_existing()
        imported = self._make_imported()
        merged_once = merge_with_catalog(existing, imported)
        merged_twice = merge_with_catalog(merged_once, imported)
        # Same number of models; same IDs
        assert {m.id for m in merged_once} == {m.id for m in merged_twice}

    def test_empty_imported(self):
        existing = self._make_existing()
        merged = merge_with_catalog(existing, [])
        assert {m.id for m in merged} == {m.id for m in existing}

    def test_empty_existing(self):
        imported = self._make_imported()
        merged = merge_with_catalog([], imported)
        assert {m.id for m in merged} == {m.id for m in imported}


# ---------------------------------------------------------------------------
# Tests for verified_free_fallback
# ---------------------------------------------------------------------------

class TestVerifiedFreeFallback:
    def _catalog(self) -> list[CatalogModel]:
        return [
            CatalogModel(
                id="premium-model",
                tier="premium",
                enabled=True,
                verified=True,
                executor_compat=["zen"],
            ),
            CatalogModel(
                id="free-unverified",
                tier="free",
                enabled=True,
                verified=False,
                executor_compat=["zen"],
            ),
            CatalogModel(
                id="free-verified",
                tier="free",
                enabled=True,
                verified=True,
                executor_compat=["zen"],
            ),
            CatalogModel(
                id="free-verified-tools",
                tier="free",
                enabled=True,
                verified=True,
                supports_tools=True,
                executor_compat=["zen"],
            ),
            CatalogModel(
                id="free-verified-disabled",
                tier="free",
                enabled=False,
                verified=True,
                executor_compat=["zen"],
            ),
            CatalogModel(
                id="free-verified-opencode",
                tier="free",
                enabled=True,
                verified=True,
                executor_compat=["opencode"],
            ),
        ]

    def test_returns_verified_free_model(self):
        cat = self._catalog()
        result = verified_free_fallback(cat)
        assert result is not None
        assert result.tier == "free"
        assert result.verified is True

    def test_unverified_not_returned(self):
        cat = [
            CatalogModel(id="free-unverified", tier="free", enabled=True, verified=False),
        ]
        assert verified_free_fallback(cat) is None

    def test_premium_not_returned(self):
        cat = [
            CatalogModel(id="premium", tier="premium", enabled=True, verified=True),
        ]
        assert verified_free_fallback(cat) is None

    def test_disabled_not_returned(self):
        cat = self._catalog()
        result = verified_free_fallback(cat, executor="zen")
        # free-verified-disabled has enabled=False → should not be returned
        assert result is not None
        assert result.id != "free-verified-disabled"

    def test_executor_filter(self):
        cat = self._catalog()
        result = verified_free_fallback(cat, executor="opencode")
        assert result is not None
        assert result.id == "free-verified-opencode"

    def test_require_tools_filters_none_and_false(self):
        cat = self._catalog()
        result = verified_free_fallback(cat, require_tools=True)
        assert result is not None
        assert result.supports_tools is True

    def test_require_tools_with_none_supports_tools(self):
        cat = [
            CatalogModel(
                id="free-tools-unknown",
                tier="free",
                enabled=True,
                verified=True,
                supports_tools=None,
                executor_compat=["zen"],
            ),
        ]
        assert verified_free_fallback(cat, require_tools=True) is None

    def test_empty_catalog(self):
        assert verified_free_fallback([]) is None


# ---------------------------------------------------------------------------
# Serialization round-trip test
# ---------------------------------------------------------------------------

class TestSerializationRoundTrip:
    def test_round_trip_with_v2_fields(self):
        original = CatalogModel(
            id="gemini-3.5-flash",
            name="Gemini 3.5 Flash",
            provider="google-gemini",
            tier="free",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            context_window=1_000_000,
            modalities=["audio", "text"],
            rate_limit={"rpm": 15, "rpd": 1500},
            auth_requirement="none",
            api_key_url="https://aistudio.google.com/app/apikey",
            supports_tools=None,
            source_url="https://freellm.net/models/google-gemini/gemini-3-5-flash/",
            upstream_model_id="gemini-3.5-flash",
            source_updated_at="2026-07-14",
            verified=False,
        )
        d = original.to_dict()
        restored = CatalogModel.from_dict(d)

        assert restored.id == original.id
        assert restored.base_url == original.base_url
        assert restored.context_window == original.context_window
        assert restored.modalities == original.modalities
        assert restored.rate_limit == original.rate_limit
        assert restored.auth_requirement == original.auth_requirement
        assert restored.api_key_url == original.api_key_url
        assert restored.supports_tools is None
        assert restored.source_url == original.source_url
        assert restored.upstream_model_id == original.upstream_model_id
        assert restored.source_updated_at == original.source_updated_at
        assert restored.verified is False

    def test_round_trip_old_format_no_v2_fields(self):
        """Old-format JSON without v2 fields should deserialize with safe defaults."""
        old_json = {
            "id": "claude-opus-4-8",
            "name": "Claude Opus 4.8",
            "provider": "anthropic",
            "tier": "premium",
            "input_cost_per_1m": 15.0,
            "output_cost_per_1m": 75.0,
            "executor_compat": ["zen", "opencode"],
            "strengths": ["plan"],
            "enabled": True,
        }
        m = CatalogModel.from_dict(old_json)
        assert m.base_url == ""
        assert m.context_window == 0
        assert m.modalities == []
        assert m.rate_limit == {}
        assert m.supports_tools is None
        assert m.verified is False

    def test_to_dict_omits_default_v2_fields(self):
        """to_dict() must not emit v2 keys when they hold default values."""
        m = CatalogModel(id="x", name="X")
        d = m.to_dict()
        assert "base_url" not in d
        assert "context_window" not in d
        assert "verified" not in d
        assert "supports_tools" not in d

    def test_explicit_empty_executor_compat_round_trip(self):
        original = CatalogModel(id="groq:model", executor_compat=[])
        restored = CatalogModel.from_dict(original.to_dict())
        assert restored.executor_compat == []

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(True, True), (False, False), ("true", True), ("false", False), ("yes", None)],
    )
    def test_supports_tools_conservative_bool_parsing(self, value, expected):
        model = CatalogModel.from_dict({"id": "x", "supports_tools": value})
        assert model.supports_tools is expected

    def test_json_serializable(self):
        models = parse_readme_text(FIXTURE_README)
        payload = [m.to_dict() for m in models]
        # Must not raise
        serialized = json.dumps(payload)
        restored = json.loads(serialized)
        assert len(restored) == len(models)


# ---------------------------------------------------------------------------
# parse_readme(path) — filesystem tests
# ---------------------------------------------------------------------------

def test_parse_readme_from_file(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(FIXTURE_README, encoding="utf-8")
    models = parse_readme(readme)
    assert len(models) > 0


def test_parse_readme_from_directory(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(FIXTURE_README, encoding="utf-8")
    models = parse_readme(tmp_path)  # pass directory
    assert len(models) > 0


def test_parse_readme_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        parse_readme(tmp_path / "nonexistent.md")


# ---------------------------------------------------------------------------
# Mock remote push test
# ---------------------------------------------------------------------------

def test_import_freellm_cli_push(tmp_path: Path, monkeypatch):
    """CLI import-freellm --push must call CatalogClient.sync_models."""
    from click.testing import CliRunner
    from voly.cli.commands.catalog import catalog_import_freellm

    readme = tmp_path / "README.md"
    readme.write_text(FIXTURE_README, encoding="utf-8")

    # Monkeypatch catalog store to use tmp_path
    import voly.catalog.store as store_module
    monkeypatch.setattr(store_module, "catalog_path", lambda base=None: tmp_path / ".voly/catalog/models.json")

    mock_client = MagicMock()
    mock_client.sync_models.return_value = {"ok": True, "upserted": 7}

    with patch("voly.catalog.client.CatalogClient.from_env", return_value=mock_client):
        runner = CliRunner()
        result = runner.invoke(
            catalog_import_freellm,
            [str(readme), "--push"],
        )

    assert result.exit_code == 0, result.output
    mock_client.sync_models.assert_called_once()
    call_args = mock_client.sync_models.call_args[0][0]
    assert isinstance(call_args, list)
    assert len(call_args) > 0


def test_import_freellm_cli_dry_run(tmp_path: Path):
    """--dry-run must not write any file."""
    from click.testing import CliRunner
    from voly.cli.commands.catalog import catalog_import_freellm

    readme = tmp_path / "README.md"
    readme.write_text(FIXTURE_README, encoding="utf-8")
    catalog_file = tmp_path / ".voly" / "catalog" / "models.json"

    runner = CliRunner()
    result = runner.invoke(catalog_import_freellm, [str(readme), "--dry-run"])

    assert result.exit_code == 0
    assert not catalog_file.exists()


def test_import_freellm_cli_json_output(tmp_path: Path):
    """--json flag must output valid JSON array."""
    from click.testing import CliRunner
    from voly.cli.commands.catalog import catalog_import_freellm

    readme = tmp_path / "README.md"
    readme.write_text(FIXTURE_README, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(catalog_import_freellm, [str(readme), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 7
