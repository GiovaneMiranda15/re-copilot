"""Provedores de LLM do motor. Os pipelines dependem só do protocolo `LLM`; o provedor é escolhido pela especificação.

Especificações aceitas por `get_llm`:
- `auto`: o primeiro disponível entre `claude` (CLI), `anthropic` (credencial da API) e `openai` (`OPENAI_API_KEY`);
- `claude[:modelo]`: Claude Code em modo headless (`claude -p`), sem chave de API;
- `anthropic[:modelo]`: API da Anthropic pelo SDK oficial (extra `anthropic`);
- `openai[:modelo]`: qualquer API compatível com OpenAI; `OPENAI_BASE_URL` muda o endereço;
- `ollama[:modelo]`: Ollama local pela API compatível com OpenAI (`OLLAMA_HOST`, padrão http://localhost:11434).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Protocol

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3.1"


class LLM(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...


class ClaudeCliLLM:
    """Usa o Claude Code em modo headless (`claude -p`), sem ferramentas. Não exige chave de API."""

    def __init__(self, model: str | None = None, timeout_s: int = 180) -> None:
        self.model = model
        self.timeout_s = timeout_s
        self.name = f"claude-cli:{model or 'default'}"

    def complete(self, prompt: str) -> str:
        argv = ["claude", "-p", "--output-format", "json", "--no-session-persistence", "--permission-mode", "dontAsk"]
        if self.model:
            argv += ["--model", self.model]
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(argv, input=prompt, capture_output=True, text=True, timeout=self.timeout_s, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"claude -p falhou (exit {result.returncode}): {result.stderr.strip()[:300]}")
        payload = json.loads(result.stdout)
        if payload.get("is_error"):
            raise RuntimeError(f"claude -p retornou erro: {str(payload.get('result'))[:300]}")
        return payload.get("result", "")


class AnthropicLLM:
    """API da Anthropic pelo SDK oficial. As credenciais vêm do ambiente (ANTHROPIC_API_KEY ou perfil do `ant`).

    As tarefas do motor (avaliar trechos, decompor consultas, resumir) são curtas: esforço baixo. Recusa por política
    vira `RuntimeError`, e o pipeline degrada para a busca simples, registrando no trace.
    """

    def __init__(self, model: str | None = None, max_tokens: int = 8000, client=None) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depende do extra instalado
                raise RuntimeError("SDK da Anthropic não instalado: instale o extra `anthropic`.") from exc
            client = anthropic.Anthropic()
        self._client = client
        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self.max_tokens = max_tokens
        self.name = f"anthropic:{self.model}"

    def complete(self, prompt: str) -> str:
        import anthropic

        params = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "output_config": {"effort": "low"},
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            if self.model.startswith(("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")):
                response = self._client.beta.messages.create(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                response = self._client.messages.create(**params)
        except anthropic.RateLimitError as exc:
            raise RuntimeError(f"limite de uso da API (429): {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"API da Anthropic respondeu {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise RuntimeError(f"sem conexão com a API da Anthropic: {exc}") from exc
        if response.stop_reason == "refusal":
            categoria = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise RuntimeError(f"modelo recusou a tarefa (categoria: {categoria})")
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAICompatibleLLM:
    """Qualquer servidor com a API de chat compatível com OpenAI (OpenAI, Ollama, vLLM, LM Studio, gateways)."""

    def __init__(self, model: str, base_url: str, api_key: str | None, label: str, timeout_s: int = 180) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.name = f"{label}:{model}"

    def complete(self, prompt: str) -> str:
        body = json.dumps({"model": self.model, "messages": [{"role": "user", "content": prompt}]}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(f"{self.base_url}/chat/completions", data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{self.name} respondeu {exc.code}: {exc.read().decode(errors='replace')[:200]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"sem conexão com {self.base_url}: {exc}") from exc
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"resposta inesperada de {self.name}: {str(payload)[:200]}") from exc


def _anthropic_available() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(shutil.which("ant")) and os.path.isdir(os.path.expanduser("~/.config/anthropic"))


def get_llm(spec: str) -> LLM:
    kind, _, arg = spec.partition(":")
    if kind == "auto":
        if shutil.which("claude"):
            return ClaudeCliLLM(model=arg or None)
        if _anthropic_available():
            return AnthropicLLM(model=arg or None)
        if os.environ.get("OPENAI_API_KEY"):
            return get_llm(f"openai:{arg}" if arg else "openai")
        raise RuntimeError("nenhum LLM disponível: instale o Claude Code, configure a API da Anthropic, "
                           "defina OPENAI_API_KEY ou use `ollama`; ou rode com `--llm none`")
    if kind == "claude":
        return ClaudeCliLLM(model=arg or None)
    if kind == "anthropic":
        return AnthropicLLM(model=arg or None)
    if kind == "openai":
        return OpenAICompatibleLLM(arg or DEFAULT_OPENAI_MODEL, os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                                   os.environ.get("OPENAI_API_KEY"), "openai")
    if kind == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        return OpenAICompatibleLLM(arg or DEFAULT_OLLAMA_MODEL, f"{host.rstrip('/')}/v1", None, "ollama")
    raise ValueError(f"LLM desconhecido: {spec} (use auto, claude, anthropic, openai, ollama ou none)")


def parse_json(text: str) -> dict | list:
    """Extrai o primeiro objeto/array JSON de uma resposta de LLM (tolera texto e cercas ```)."""
    fence = re.search(r"```(?:json)?\s*([\[{].*[\]}])\s*```", text, re.S)
    candidates = [fence.group(1)] if fence else []
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"resposta sem JSON válido: {text[:200]}")
