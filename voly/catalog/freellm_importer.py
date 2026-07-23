"""Parse awesome-freellm-apis README into CatalogModel entries.

Data origin: https://github.com/open-free-llm-api/awesome-free-llm-apis (MIT)
This module is read-only with respect to the external repository — it never
writes back to it and never makes network calls.

Parsed sections (identified by HTML comment markers):
  <!-- BEGIN_QUICK_REF -->   — provider base URLs and API key links
  <!-- BEGIN_PERMANENT_FREE --> — provider modalities / auth requirements
  <!-- BEGIN_BEST_MODELS -->   — per-model context, rate limits

All returned CatalogModel instances have verified=False by default.
Set verified=True manually or via a future verification step before using
in verified_free_fallback().
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from voly.catalog.types import CatalogModel

# The README emits the date it was last updated inside this comment block.
_LAST_UPDATED_RE = re.compile(
    r"<!-- AUTO_LAST_UPDATED -->\s*\n([\d-]+)", re.MULTILINE
)

SOURCE_REPO = "https://github.com/open-free-llm-api/awesome-free-llm-apis"

_CREDIT_CARD_LABEL = "credit card"


# ---------------------------------------------------------------------------
# Internal provider info gathered while parsing multiple sections
# ---------------------------------------------------------------------------

@dataclass
class _ProviderInfo:
    base_url: str = ""
    api_key_url: str = ""
    auth_requirement: str = ""  # none | email | phone | credit_card
    modalities: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Low-level text helpers
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """Return inner text of the first <a>…</a>, then strip any remaining tags."""
    text = re.sub(r'<a[^>]*>([^<]*)</a>', r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def _extract_href(text: str) -> str:
    """Extract the href value from the first <a href="…"> in text."""
    m = re.search(r'<a[^>]*href="([^"]*)"', text, re.IGNORECASE)
    return m.group(1) if m else ""


def _strip_backtick(text: str) -> str:
    return text.strip().strip('`').strip()


def _parse_context_window(text: str) -> int:
    """Parse '262K' → 262000, '1M' → 1_000_000, '0' or '' → 0."""
    text = text.strip()
    if not text or text == "0":
        return 0
    m = re.match(r"^([\d.]+)([KMG]?)$", text, re.IGNORECASE)
    if not m:
        return 0
    val = float(m.group(1))
    suffix = m.group(2).upper()
    multipliers = {"K": 1_000, "M": 1_000_000, "G": 1_000_000_000}
    return int(val * multipliers.get(suffix, 1))


def _parse_rate_limit(text: str) -> dict[str, Any]:
    """Convert rate-limit strings to a structured dict.

    Recognised units: RPM, RPD, RPS, TPM, TPD (with optional K/M suffix).
    Unrecognised formats are stored under the 'raw' key.
    Returns an empty dict when the text is clearly 'see provider' / empty.
    """
    raw = text.strip()
    if not raw or re.match(r'^see\s+provider$', raw, re.IGNORECASE):
        return {}

    # Normalise: remove "Up to", "~", parenthetical notes, strip commas in numbers
    cleaned = re.sub(r'\bup\s+to\b', '', raw, flags=re.IGNORECASE)
    cleaned = cleaned.replace('~', '')
    cleaned = re.sub(r'\([^)]*\)', '', cleaned)  # strip (anonymous) etc.
    # Remove numeric comma separators, e.g. 14,400 → 14400
    cleaned = re.sub(r'(\d),(\d)', r'\1\2', cleaned)

    result: dict[str, Any] = {}
    pattern = re.compile(
        r'([\d.]+)([KMG]?)\s*(RPM|RPD|RPS|TPM|TPD)',
        re.IGNORECASE,
    )
    suffix_mult = {"K": 1_000, "M": 1_000_000, "G": 1_000_000_000}
    unit_key = {
        "RPM": "rpm", "RPD": "rpd", "RPS": "rps",
        "TPM": "tpm", "TPD": "tpd",
    }

    for m in pattern.finditer(cleaned):
        val = float(m.group(1))
        mult = suffix_mult.get(m.group(2).upper(), 1)
        unit = m.group(3).upper()
        key = unit_key[unit]
        final = int(val * mult) if unit != "RPS" else round(val * mult, 3)
        result[key] = final

    if not result:
        result["raw"] = raw
    return result


def _parse_auth(text: str) -> str:
    """Normalise free-tier auth descriptions to a canonical label."""
    t = text.strip().lower()
    if t in ("no", "none", ""):
        return "none"
    if "phone" in t:
        return "phone"
    if _CREDIT_CARD_LABEL in t or "creditcard" in t:
        return "credit_card"
    # "Registration" / "Email" → email-based signup
    return "email"


def _parse_modalities(text: str) -> list[str]:
    """Split 'audio, image, text' into a list."""
    return [m.strip() for m in text.split(",") if m.strip()]


# ---------------------------------------------------------------------------
# Markdown table parser
# ---------------------------------------------------------------------------

def _parse_md_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Return (header_columns, data_rows) from a Markdown table.

    Columns in the header row are lowercased and stripped.
    Separator rows (|---|...) are dropped automatically.
    """
    all_rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        # Separator: every non-empty cell matches only dashes/colons
        if cells and all(re.match(r'^[-: ]+$', c) for c in cells if c):
            continue
        all_rows.append(cells)

    if not all_rows:
        return [], []

    header = [_strip_html(c).lower().strip() for c in all_rows[0]]
    return header, all_rows[1:]


def _col(header: list[str], *names: str) -> int:
    """Return first column index matching any of the given lowercased names."""
    for name in names:
        for i, h in enumerate(header):
            if name in h:
                return i
    return -1


def _cell(row: list[str], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return row[idx].strip()


# ---------------------------------------------------------------------------
# Section extractors
# ---------------------------------------------------------------------------

def _extract_section(content: str, begin: str, end: str) -> str:
    start = content.find(begin)
    stop = content.find(end)
    if start == -1 or stop == -1 or stop <= start:
        return ""
    return content[start + len(begin):stop]


def _parse_quick_ref(content: str) -> dict[str, _ProviderInfo]:
    """Parse <!-- BEGIN_QUICK_REF --> section.

    Columns: Provider | Base URL | Get API Key | Credit Card?
    """
    section = _extract_section(content, "<!-- BEGIN_QUICK_REF -->", "<!-- END_QUICK_REF -->")
    if not section:
        return {}

    header, rows = _parse_md_table(section)
    provider_col = _col(header, "provider")
    url_col = _col(header, "base url", "url")
    key_col = _col(header, "get api key", "api key", "key")
    auth_col = _col(header, _CREDIT_CARD_LABEL, "auth", "card")

    result: dict[str, _ProviderInfo] = {}
    for row in rows:
        name = _strip_html(_cell(row, provider_col))
        if not name:
            continue
        base_url = _strip_backtick(_cell(row, url_col))
        api_key_url = _extract_href(_cell(row, key_col))
        auth = _parse_auth(_strip_html(_cell(row, auth_col)))
        result[name] = _ProviderInfo(
            base_url=base_url,
            api_key_url=api_key_url,
            auth_requirement=auth,
        )
    return result


def _enrich_provider_from_row(
    info: _ProviderInfo, row: list[str], modalities_col: int, auth_col: int, key_col: int
) -> None:
    if modalities_col >= 0:
        raw_mod = _strip_html(_cell(row, modalities_col))
        if raw_mod:
            info.modalities = _parse_modalities(raw_mod)
    if auth_col >= 0 and not info.auth_requirement:
        info.auth_requirement = _parse_auth(_strip_html(_cell(row, auth_col)))
    if key_col >= 0 and not info.api_key_url:
        info.api_key_url = _extract_href(_cell(row, key_col))


def _parse_permanent_free(content: str, providers: dict[str, _ProviderInfo]) -> None:
    """Enrich `providers` dict with modalities from <!-- BEGIN_PERMANENT_FREE --> section.

    Columns: Provider | Free Models | Credit Card? | Max Context | Modalities | Get API Key
    Mutates providers in-place; adds new entries if not already present.
    """
    section = _extract_section(
        content, "<!-- BEGIN_PERMANENT_FREE -->", "<!-- END_PERMANENT_FREE -->"
    )
    if not section:
        return

    header, rows = _parse_md_table(section)
    provider_col = _col(header, "provider")
    auth_col = _col(header, _CREDIT_CARD_LABEL, "auth", "card")
    modalities_col = _col(header, "modalities", "modal")
    key_col = _col(header, "get api key", "api key", "key")

    for row in rows:
        name = _strip_html(_cell(row, provider_col))
        if not name:
            continue
        if name not in providers:
            providers[name] = _ProviderInfo()
        _enrich_provider_from_row(providers[name], row, modalities_col, auth_col, key_col)


def _parse_best_models(
    content: str,
    providers: dict[str, _ProviderInfo],
    source_updated_at: str,
) -> list[CatalogModel]:
    """Parse <!-- BEGIN_BEST_MODELS --> section into CatalogModel entries.

    Columns: Provider | Best Free Model | Model ID | Max Context | Rate Limit

    Provider cell may be empty (carry-forward from previous row).
    """
    section = _extract_section(
        content, "<!-- BEGIN_BEST_MODELS -->", "<!-- END_BEST_MODELS -->"
    )
    if not section:
        return []

    header, rows = _parse_md_table(section)
    provider_col = _col(header, "provider")
    name_col = _col(header, "best free model", "model name", "model")
    id_col = _col(header, "model id", "id")
    ctx_col = _col(header, "max context", "context")
    rl_col = _col(header, "rate limit", "rate")

    models: list[CatalogModel] = []
    current_provider = ""

    for row in rows:
        raw_provider = _strip_html(_cell(row, provider_col))
        if raw_provider:
            current_provider = raw_provider

        if not current_provider:
            continue  # skip rows with no resolved provider

        # Model name: strip HTML to get display text; href is source_url
        raw_name_cell = _cell(row, name_col)
        source_url = _extract_href(raw_name_cell)
        display_name = _strip_html(raw_name_cell)

        # Model ID: strip backticks
        model_id = _strip_backtick(_strip_html(_cell(row, id_col)))
        if not model_id:
            model_id = display_name  # fallback to display name if no separate ID
        if not model_id:
            continue  # skip rows we can't derive an ID from

        # Numeric metadata
        context_window = _parse_context_window(_strip_html(_cell(row, ctx_col)))
        rate_limit = _parse_rate_limit(_strip_html(_cell(row, rl_col)))

        # Enrich from provider dict
        info = providers.get(current_provider, _ProviderInfo())
        provider_slug = _provider_slug(current_provider)

        # Catalog IDs are provider-qualified because the same upstream model ID
        # can be offered by multiple providers with different endpoints/limits.
        catalog_id = f"{provider_slug}:{model_id}"
        models.append(
            CatalogModel(
                id=catalog_id,
                name=display_name or model_id,
                provider=provider_slug,
                tier="free",
                input_cost_per_1m=0.0,
                output_cost_per_1m=0.0,
                # The source does not describe VOLY executor compatibility.
                executor_compat=[],
                strengths=[],
                enabled=True,
                base_url=info.base_url,
                context_window=context_window,
                modalities=list(info.modalities),
                rate_limit=rate_limit,
                auth_requirement=info.auth_requirement,
                api_key_url=info.api_key_url,
                supports_tools=None,  # not knowable from README
                source_url=source_url or SOURCE_REPO,
                upstream_model_id=model_id,
                source_updated_at=source_updated_at,
                verified=False,  # must be set explicitly
                last_verified_at="",
            )
        )

    return models


# ---------------------------------------------------------------------------
# Provider slug normalisation
# ---------------------------------------------------------------------------

_PROVIDER_SLUG_OVERRIDES: dict[str, str] = {
    "NVIDIA NIM": "nvidia-nim",
    "ModelScope": "modelscope",
    "Cloudflare Workers AI": "cloudflare-workers-ai",
    "OpenRouter": "openrouter",
    "GitHub Models": "github-models",
    "Google Gemini": "google-gemini",
    "OVHcloud AI Endpoints": "ovhcloud",
    "Groq": "groq",
    "Mistral AI": "mistral",
    "LLM7.io": "llm7",
    "Cerebras": "cerebras",
    "Cohere": "cohere",
    "Ollama Cloud": "ollama-cloud",
    "OpenCode Zen": "opencode-zen",
    "Agnes AI": "agnes-ai",
    "Aion Labs": "aion-labs",
    "Hugging Face": "huggingface",
    "Kilo Code": "kilo-code",
    "Alibaba Cloud Model Studio": "alibaba-cloud",
    "Z AI (Zhipu AI)": "zhipu-ai",
    "SambaNova": "sambanova",
    "SiliconFlow": "siliconflow",
    "xAI": "xai",
    "Chutes.ai": "chutes",
    "Glhf.chat": "glhf",
    "Grok (xAI)": "grok-xai",
    "AI21 Labs": "ai21",
    "DeepSeek": "deepseek",
    "Nscale": "nscale",
    "Nebius": "nebius",
}


def _provider_slug(name: str) -> str:
    if name in _PROVIDER_SLUG_OVERRIDES:
        return _PROVIDER_SLUG_OVERRIDES[name]
    # Fallback: lowercase, replace non-alnum with dash
    s = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return s.strip("-")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_readme(source: Path) -> list[CatalogModel]:
    """Parse awesome-freellm-apis README at *source* into CatalogModel entries.

    *source* can be:
    - the README.md file directly, or
    - the root directory of the awesome-freellm-apis checkout (README.md inside).

    Returns a deduplicated list of CatalogModel entries.
    All returned models have verified=False; the caller must set verified=True
    explicitly after manual or automated verification.

    Raises FileNotFoundError if the README cannot be located.
    Raises ValueError if no parseable sections are found.
    """
    path = Path(source)
    if path.is_dir():
        path = path / "README.md"
    if not path.is_file():
        raise FileNotFoundError(f"README not found at {path}")

    content = path.read_text(encoding="utf-8")
    return parse_readme_text(content)


def parse_readme_text(content: str) -> list[CatalogModel]:
    """Parse README content string — exposed for testing without filesystem."""
    # Extract the last-updated date if present
    m = _LAST_UPDATED_RE.search(content)
    source_updated_at = m.group(1).strip() if m else ""

    # Build provider metadata from Quick Reference and Permanent Free sections
    providers: dict[str, _ProviderInfo] = _parse_quick_ref(content)
    _parse_permanent_free(content, providers)

    models = _parse_best_models(content, providers, source_updated_at)

    if not models:
        raise ValueError(
            "No models parsed from README. "
            "Expected <!-- BEGIN_BEST_MODELS --> section with data rows."
        )

    # Deduplicate exact provider/model pairs. Provider-qualified IDs preserve
    # the same upstream model offered by multiple providers.
    seen: dict[str, CatalogModel] = {}
    for model in models:
        seen[model.id] = model
    return list(seen.values())


def _find_legacy_id(result: dict[str, CatalogModel], imp: CatalogModel) -> str | None:
    """Find an existing legacy row whose ID is the raw upstream model ID,
    matched only when the provider also matches."""
    return next(
        (
            model_id
            for model_id, model in result.items()
            if model.id == imp.upstream_model_id and model.provider == imp.provider
        ),
        None,
    )


def _merge_model(ex: CatalogModel, imp: CatalogModel) -> CatalogModel:
    return CatalogModel(
        id=ex.id,
        name=ex.name or imp.name,
        provider=ex.provider or imp.provider,
        # Preserve routing/cost fields from existing
        tier=ex.tier,
        input_cost_per_1m=ex.input_cost_per_1m,
        output_cost_per_1m=ex.output_cost_per_1m,
        executor_compat=ex.executor_compat,
        strengths=ex.strengths,
        enabled=ex.enabled,
        # Enrich with freellm metadata; fall back to existing if imported empty
        base_url=imp.base_url or ex.base_url,
        context_window=imp.context_window or ex.context_window,
        modalities=imp.modalities or ex.modalities,
        rate_limit=imp.rate_limit or ex.rate_limit,
        auth_requirement=imp.auth_requirement or ex.auth_requirement,
        api_key_url=imp.api_key_url or ex.api_key_url,
        # supports_tools: keep existing if set; don't downgrade to None
        supports_tools=ex.supports_tools if ex.supports_tools is not None else imp.supports_tools,
        source_url=imp.source_url or ex.source_url,
        upstream_model_id=ex.upstream_model_id or imp.upstream_model_id,
        source_updated_at=imp.source_updated_at or ex.source_updated_at,
        # Never clear a verified flag from existing
        verified=ex.verified,
        last_verified_at=ex.last_verified_at,
    )


def merge_with_catalog(
    existing: list[CatalogModel],
    imported: list[CatalogModel],
) -> list[CatalogModel]:
    """Merge freellm-imported models into an existing catalog.

    Rules:
    - All existing models are preserved (none are removed).
    - New provider-qualified model IDs (not in existing) are appended.
    - Legacy raw IDs are matched only when the provider also matches.
    - For model IDs that already exist:
        - Routing fields (tier, executor_compat, strengths, enabled) are kept
          from the existing entry.
        - New metadata fields (base_url, context_window, modalities, rate_limit,
          auth_requirement, api_key_url, source_url, source_updated_at) are
          updated from the imported entry if non-empty.
        - verified / last_verified_at are always kept from existing to avoid
          accidentally clearing a manually verified flag.
    """
    result: dict[str, CatalogModel] = {m.id: m for m in existing}

    for imp in imported:
        target_id = imp.id
        if target_id not in result:
            legacy_id = _find_legacy_id(result, imp)
            if legacy_id is None:
                result[target_id] = imp
                continue
            target_id = legacy_id

        result[target_id] = _merge_model(result[target_id], imp)

    return list(result.values())
