"""Provedores de LLM: seleção e tratamento de erro, sem rede."""

from __future__ import annotations

import io
import json
import types
import urllib.error

import pytest

from rag_re_engine import llm


def test_auto_prefers_claude_cli(monkeypatch) -> None:
    monkeypatch.setattr(llm.shutil, "which", lambda name: "/bin/claude" if name == "claude" else None)
    assert isinstance(llm.get_llm("auto"), llm.ClaudeCliLLM)


def test_auto_falls_back_to_openai_then_errors(monkeypatch) -> None:
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    monkeypatch.setattr(llm, "_anthropic_available", lambda: False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert llm.get_llm("auto").name.startswith("openai:")
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(RuntimeError, match="nenhum LLM"):
        llm.get_llm("auto")


def test_ollama_uses_local_openai_compatible_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://h:1")
    model = llm.get_llm("ollama:qwen")
    assert model.base_url == "http://h:1/v1" and model.name == "ollama:qwen" and model.api_key is None


def test_unknown_provider() -> None:
    with pytest.raises(ValueError):
        llm.get_llm("xpto")


def test_openai_compatible_request_and_errors(monkeypatch) -> None:
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(request, timeout):
        sent["url"], sent["body"], sent["auth"] = request.full_url, json.loads(request.data), request.get_header("Authorization")
        return Resp(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake)
    model = llm.OpenAICompatibleLLM("m", "http://x/v1", "k", "openai")
    assert model.complete("oi") == "ok"
    assert sent["url"] == "http://x/v1/chat/completions" and sent["auth"] == "Bearer k" and sent["body"]["model"] == "m"

    def fail(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "limit", {}, io.BytesIO(b"slow down"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", fail)
    with pytest.raises(RuntimeError, match="429"):
        model.complete("oi")


class FakeMessages:
    def __init__(self, response, calls):
        self.response, self.calls = response, calls

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_client(response):
    calls: list[dict] = []
    client = types.SimpleNamespace(messages=FakeMessages(response, calls),
                                   beta=types.SimpleNamespace(messages=FakeMessages(response, calls)))
    return client, calls


def test_anthropic_extracts_text_and_uses_fallbacks_on_opus() -> None:
    pytest.importorskip("anthropic")
    response = types.SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[
        types.SimpleNamespace(type="thinking", thinking=""), types.SimpleNamespace(type="text", text='{"a": 1}')])
    client, calls = fake_client(response)
    assert llm.AnthropicLLM(client=client).complete("x") == '{"a": 1}'
    assert calls[0]["model"] == "claude-opus-5-5" and calls[0]["fallbacks"] == "default"
    assert calls[0]["output_config"] == {"effort": "low"}
    client2, calls2 = fake_client(response)
    llm.AnthropicLLM(model="claude-haiku-5-5", client=client2).complete("x")
    assert "fallbacks" not in calls2[0]


def test_anthropic_refusal_becomes_runtime_error() -> None:
    pytest.importorskip("anthropic")
    response = types.SimpleNamespace(stop_reason="refusal", stop_details=types.SimpleNamespace(category="cyber"), content=[])
    client, _ = fake_client(response)
    with pytest.raises(RuntimeError, match="recusou"):
        llm.AnthropicLLM(client=client).complete("x")
