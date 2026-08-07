"""AI provider selection and status.

Provider is chosen from AI_PROVIDER; if that is unset/'none'/'auto', it is inferred
from whichever API key is present. This means simply adding ANTHROPIC_API_KEY (or
OPENAI_API_KEY) activates the AI without any other configuration. When no provider is
available, the offline provider is used (deterministic, data-grounded — never a
dead-end message).
"""

from __future__ import annotations

from functools import lru_cache

from ..core.config import get_settings
from .base import AIProvider
from .stub_provider import StubProvider


def _resolve_provider_name(s) -> str:
    """Return the effective provider name: 'anthropic' | 'openai' | 'none'."""
    pref = (s.ai_provider or "").strip().lower()
    if pref in ("anthropic", "openai"):
        return pref
    # unset / 'none' / 'auto' → infer from available keys
    if s.anthropic_api_key:
        return "anthropic"
    if s.openai_api_key:
        return "openai"
    return "none"


def _key_for(provider: str, s) -> str:
    return {"anthropic": s.anthropic_api_key, "openai": s.openai_api_key}.get(provider, "")


@lru_cache
def get_ai_provider() -> AIProvider:
    s = get_settings()
    provider = _resolve_provider_name(s)
    key = _key_for(provider, s)

    if provider == "anthropic" and key:
        try:
            from .anthropic_provider import AnthropicProvider

            return AnthropicProvider(api_key=key, model=s.ai_model)
        except Exception:  # noqa: BLE001 — SDK missing/construct failed → offline
            return StubProvider()

    if provider == "openai" and key:
        try:
            from .openai_provider import OpenAIProvider

            return OpenAIProvider(api_key=key, model=s.ai_model)
        except Exception:  # noqa: BLE001
            return StubProvider()

    return StubProvider()


def ai_status() -> dict:
    """Report the current AI configuration without making a network call."""
    s = get_settings()
    provider = _resolve_provider_name(s)
    key = _key_for(provider, s)
    active = getattr(get_ai_provider(), "name", "stub")
    using_llm = active in ("anthropic", "openai")

    if provider == "none":
        message = (
            "No AI provider configured. Set AI_PROVIDER=anthropic and ANTHROPIC_API_KEY "
            "(or AI_PROVIDER=openai and OPENAI_API_KEY) in apps/api/.env, then restart the API. "
            "The deterministic engine and offline analysis remain fully functional."
        )
        return {
            "configured": False, "provider": provider, "active_provider": active,
            "model": s.ai_model, "using_llm": using_llm, "ready": False, "message": message,
        }

    if not key:
        message = (
            f"AI_PROVIDER is '{provider}' but the corresponding API key is not set. "
            f"Add the API key to apps/api/.env and restart the API."
        )
        return {
            "configured": False, "provider": provider, "active_provider": active,
            "model": s.ai_model, "using_llm": using_llm, "ready": False, "message": message,
        }

    if not using_llm:
        message = (
            f"A key for '{provider}' is set but the SDK could not be loaded. "
            f"Install it: pip install -e \".[ai]\"."
        )
        return {
            "configured": True, "provider": provider, "active_provider": active,
            "model": s.ai_model, "using_llm": False, "ready": False, "message": message,
        }

    return {
        "configured": True, "provider": provider, "active_provider": active,
        "model": s.ai_model, "using_llm": True, "ready": True,
        "message": f"AI provider '{provider}' active (model {s.ai_model}). "
        "Run a live check with POST /api/ai/verify.",
    }


def verify_ai() -> dict:
    """Make a minimal live call to confirm the key/model actually work."""
    provider = get_ai_provider()
    if not hasattr(provider, "verify"):
        return {"ok": False, "provider": getattr(provider, "name", "stub"),
                "error": "No live AI provider configured."}
    try:
        provider.verify()  # type: ignore[attr-defined]
        return {"ok": True, "provider": provider.name, "error": None}
    except Exception as e:  # noqa: BLE001
        from .anthropic_provider import _describe_error

        return {"ok": False, "provider": provider.name, "error": _describe_error(e)}
