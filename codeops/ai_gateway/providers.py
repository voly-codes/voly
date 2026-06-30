"""Provider call implementations — mixin for AIGateway."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

_log = logging.getLogger("codeops.ai_gateway.providers")


class _GatewayProvidersMixin:
    """Low-level API call methods for each LLM provider.
    Expects self.account_id, self.gateway_id, self.api_token from AIGateway."""

    # ── Format adapters ─────────────────────────────────────────────────────────

    def _call_anthropic(
        self, url: str, messages: list, model: str, max_tokens: int,
        temperature: float, system: str | None, headers: dict,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools
        req = urllib.request.Request(
            f"{url}/v1/messages", data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                msg = json.loads(body_text).get("error", {}).get("message", body_text)
            except Exception:
                msg = body_text
            raise RuntimeError(f"Anthropic {e.code}: {msg}") from e
        return {
            "content": "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            ),
            "model": data.get("model", model),
            "usage": {
                "input_tokens":  data.get("usage", {}).get("input_tokens", 0),
                "output_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (data.get("usage", {}).get("input_tokens", 0)
                                 + data.get("usage", {}).get("output_tokens", 0)),
            },
        }

    def _call_openai(
        self, url: str, messages: list, model: str, max_tokens: int,
        temperature: float, system: str | None, headers: dict,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        msgs = list(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})
        body: dict[str, Any] = {
            "model": model, "messages": msgs,
            "max_tokens": max_tokens, "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
        req = urllib.request.Request(
            f"{url}/v1/chat/completions", data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                msg = json.loads(body_text).get("error", {}).get("message", body_text)
            except Exception:
                msg = body_text
            raise RuntimeError(f"OpenAI {e.code}: {msg}") from e
        choice = data["choices"][0]
        return {
            "content": choice["message"].get("content", ""),
            "model": data.get("model", model),
            "usage": {
                "input_tokens":  data.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
                "total_tokens":  data.get("usage", {}).get("total_tokens", 0),
            },
        }

    def _call_google(
        self, url: str, messages: list, model: str, max_tokens: int,
        temperature: float, system: str | None, headers: dict,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = [{"text": msg["content"]}] if isinstance(msg["content"], str) else msg["content"]
            contents.append({"role": role, "parts": parts})
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": tools}]
        req = urllib.request.Request(
            f"{url}/v1beta/models/{model}:generateContent",
            data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                msg = json.loads(body_text).get("error", {}).get("message", body_text)
            except Exception:
                msg = body_text
            raise RuntimeError(f"Google {e.code}: {msg}") from e
        candidates = data.get("candidates", [{}])
        parts = candidates[0].get("content", {}).get("parts", [{"text": ""}])
        text = "".join(p.get("text", "") for p in parts)
        meta = data.get("usageMetadata", {})
        return {
            "content": text,
            "model": model,
            "usage": {
                "input_tokens":  meta.get("promptTokenCount", 0),
                "output_tokens": meta.get("candidatesTokenCount", 0),
                "total_tokens":  meta.get("promptTokenCount", 0) + meta.get("candidatesTokenCount", 0),
            },
        }

    # ── Cloudflare-specific providers ────────────────────────────────────────────

    def _call_workers_ai(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
    ) -> dict[str, Any]:
        """Cloudflare Workers AI REST API — hundreds of open models, cheap/free tier."""
        account_id = self.account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")  # type: ignore[attr-defined]
        token      = self.api_token  or os.environ.get("CLOUDFLARE_API_TOKEN", "")   # type: ignore[attr-defined]
        if not account_id or not token:
            return {"error": "workers-ai: CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN not set", "content": ""}

        if not model.startswith("@"):
            model = f"@cf/{model}"

        url  = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        msgs = list(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})
        body: dict[str, Any] = {"messages": msgs, "max_tokens": max_tokens, "temperature": temperature}
        req  = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                errs = json.loads(body_text).get("errors", [])
                msg  = errs[0].get("message", body_text) if errs else body_text
            except Exception:
                msg = body_text
            raise RuntimeError(f"WorkersAI {e.code}: {msg}") from e

        if not data.get("success", True):
            errs = data.get("errors", [])
            raise RuntimeError(f"WorkersAI error: {errs[0].get('message', 'unknown') if errs else 'unknown'}")

        result_obj = data.get("result", {})
        if not isinstance(result_obj, dict):
            result_obj = {}

        # Some CF models return OpenAI chat-completion format (gpt-oss, kimi, qwq, etc.)
        # Others return the classic Workers AI format (llama, mistral, qwen-coder, etc.)
        if "choices" in result_obj:
            # OpenAI-compat format; reasoning models put thinking in reasoning_content,
            # actual answer in content (content may be null if max_tokens hit during thinking)
            msg     = (result_obj.get("choices") or [{}])[0].get("message", {})
            content = msg.get("content") or ""   # don't use reasoning_content as answer
            usage_  = result_obj.get("usage", {})
        else:
            # Classic Workers AI format
            content = result_obj.get("response", "")
            usage_  = result_obj.get("usage", {})

        return {
            "content": content,
            "model": model,
            "usage": {
                "input_tokens":  usage_.get("prompt_tokens", 0),
                "output_tokens": usage_.get("completion_tokens", 0),
                "total_tokens":  usage_.get("total_tokens", 0),
            },
        }

    def _call_cloudflare_dynamic(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """CF AI Gateway dynamic routing — CF applies per-gateway routing rules.

        Requires dynamic routing rules configured in CF Dashboard:
        AI Gateway → {gateway_id} → Routing (Beta) → Add rules
        """
        account_id = self.account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")  # type: ignore[attr-defined]
        gateway_id = self.gateway_id or os.environ.get("CLOUDFLARE_AI_GATEWAY_ID", "default")  # type: ignore[attr-defined]
        token      = self.api_token  or os.environ.get("CLOUDFLARE_API_TOKEN", "")   # type: ignore[attr-defined]
        if not account_id:
            return {"error": "cloudflare-dynamic: CLOUDFLARE_ACCOUNT_ID not set", "content": ""}

        # Dynamic routing goes through the OpenAI-compat endpoint of CF AI Gateway.
        # model must be "dynamic/{gateway_id}" — routing rules are set in CF dashboard.
        base      = f"https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/openai"
        dyn_model = model if model.startswith("dynamic/") else f"dynamic/{gateway_id}"
        hdrs: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            hdrs["cf-aig-authorization"] = f"Bearer {token}"
        for env_key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
            val = os.environ.get(env_key, "")
            if val:
                hdrs["Authorization"] = f"Bearer {val}"
                break

        _log.info("CF dynamic routing: model=%s gateway=%s/%s", dyn_model, account_id, gateway_id)
        try:
            return self._call_openai(base, messages, dyn_model, max_tokens, temperature, system, hdrs, tools=tools)
        except RuntimeError as e:
            if "403" in str(e):
                return {
                    "error": (
                        "CF dynamic routing not configured. "
                        "Set up routing rules in CF Dashboard → AI Gateway → default → Routing (Beta). "
                        f"Original: {e}"
                    ),
                    "content": "",
                }
            raise

    # ── _direct_call: builds headers and dispatches to a format adapter ──────────

    def _direct_call(
        self,
        messages: list[dict[str, Any]],
        model: str,
        provider_name: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            if provider_name == "anthropic":
                key  = os.environ.get("ANTHROPIC_API_KEY", "")
                base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
                hdrs = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
                return self._call_anthropic(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            if provider_name == "openai":
                key  = os.environ.get("OPENAI_API_KEY", "")
                base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            if provider_name in ("google", "google-ai-studio"):
                base = os.environ.get("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com")
                hdrs = {"Content-Type": "application/json"}
                return self._call_google(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            if provider_name == "deepseek":
                key  = os.environ.get("DEEPSEEK_API_KEY", "")
                base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            if provider_name == "mimo":
                key  = os.environ.get("MIMO_API_KEY", "")
                base = os.environ.get("MIMO_BASE_URL_OPENAI", "https://token-plan-sgp.xiaomimimo.com")
                base = base[:-3] if base.endswith("/v1") else base
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            if provider_name == "mimo-anthropic":
                key  = os.environ.get("MIMO_API_KEY", "")
                base = os.environ.get("MIMO_BASE_URL_ANTHROPIC", "https://token-plan-sgp.xiaomimimo.com/anthropic")
                hdrs = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
                return self._call_anthropic(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            if provider_name == "opencode":
                key  = os.environ.get("OPENCODE_API_KEY", "")
                base = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai/zen/go")
                base = base[:-3] if base.endswith("/v1") else base
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "codeops/0.1.0"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            if provider_name == "opencode-zen":
                key  = os.environ.get("OPENCODE_API_KEY", "")
                base = os.environ.get("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen")
                base = base[:-3] if base.endswith("/v1") else base
                hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "codeops/0.1.0"}
                return self._call_openai(base, messages, model, max_tokens, temperature, system, hdrs, tools=tools)

            if provider_name == "workers-ai":
                return self._call_workers_ai(messages, model, max_tokens, temperature, system)

            if provider_name == "cloudflare-dynamic":
                return self._call_cloudflare_dynamic(messages, model, max_tokens, temperature, system, tools=tools)

            return {"error": f"Unsupported provider: {provider_name}", "content": ""}

        except Exception as e:
            self.metrics.record_error()  # type: ignore[attr-defined]
            return {"error": str(e), "content": ""}
