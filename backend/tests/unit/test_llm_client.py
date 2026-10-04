"""Unit tests for the LLM client."""
import pytest

from app.services.llm_client import LLMError, get_llm


def test_get_llm_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    # Force config reload; the test environment may not have a key set.
    monkeypatch.setattr(
        "app.services.llm_client.get_settings",
        lambda: type("S", (), {"llm_api_key": None, "llm_base_url": "https://example.com", "llm_model": "test"})(),
    )
    with pytest.raises(LLMError, match="LLM_API_KEY is not configured"):
        get_llm()
