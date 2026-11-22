"""Servidor MCP: ferramentas, prompt e recursos, chamados em processo (sem transporte)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from rag_re_engine import mcp_server  # noqa: E402


def call(name: str, **args):
    result = asyncio.run(mcp_server.mcp.call_tool(name, args))
    assert not getattr(result, "is_error", False), result
    if getattr(result, "structured_content", None) is not None:
        data = result.structured_content
        return data.get("result", data)
    return json.loads(result.content[0].text)


def test_tools_are_listed() -> None:
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {"re_init", "re_status", "re_verificar", "re_exportar", "re_ler_arquivo", "rag_indexar", "rag_buscar"} <= names


def test_prompt_and_resources_expose_the_method() -> None:
    prompt = asyncio.run(mcp_server.mcp.get_prompt("re-copilot"))
    assert "re-copilot" in prompt.messages[0].content.text
    texto = list(asyncio.run(mcp_server.mcp.read_resource("re-copilot://references/workflow.md")))[0].content
    assert "Workflow" in texto
    perfil = list(asyncio.run(mcp_server.mcp.read_resource("re-copilot://roles/financeiro")))[0].content
    assert "Financeiro" in perfil
    assert "financeiro" in call("re_indice")["perfis"]


def test_resource_rejects_path_traversal() -> None:
    with pytest.raises(Exception):
        list(asyncio.run(mcp_server.mcp.read_resource("re-copilot://references/..%2F..%2Fpyproject.toml")))


def test_project_flow_through_tools(tmp_path: Path) -> None:
    proj = str(tmp_path)
    assert call("re_init", projeto=proj, nome="teste")
    assert call("re_check", projeto=proj) == []
    assert call("re_status", projeto=proj)["projeto"] == "teste"
    model = tmp_path / ".re" / "modelo"
    (model / "backlog.json").write_text(json.dumps({"itens": [
        {"id": "EP-001", "titulo": "Épico", "status": "proposto"},
        {"id": "US-001", "titulo": "História", "pai": "EP-001", "status": "proposto"}]}))
    csv = call("re_exportar", projeto=proj, destino="jira")
    assert csv.startswith('"Issue Id"')
    assert "gerado" in call("re_exportar", projeto=proj, destino="azure", saida="out/azure.csv")
    assert (tmp_path / "out" / "azure.csv").exists()


def test_recop_refusal_becomes_tool_error(tmp_path: Path) -> None:
    call("re_init", projeto=str(tmp_path), nome="x")
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="nenhuma baseline"):
        asyncio.run(mcp_server.mcp.call_tool("re_diff", {"projeto": str(tmp_path)}))
    with pytest.raises(ToolError, match="re_init"):
        asyncio.run(mcp_server.mcp.call_tool("re_status", {"projeto": str(tmp_path / "nada")}))


def test_secret_safe_reading_tool(tmp_path: Path) -> None:
    f = tmp_path / "a.js"
    f.write_text("token: abcdefghijklmnop\n")
    assert "oculto" in call("re_ler_arquivo", caminho=str(f))


def test_rag_index_and_search_without_llm(tmp_path: Path) -> None:
    fontes = tmp_path / "fontes"
    fontes.mkdir()
    (fontes / "a.md").write_text("A comissão do vendedor é calculada pelo financeiro.")
    rel = call("rag_indexar", projeto=str(tmp_path), pasta=str(fontes), sistema="SIS-01", embedder="hash")
    assert rel["chunks"] == 1
    pacote = call("rag_buscar", projeto=str(tmp_path), atividade="elicitacao", consulta="comissão", llm="none")
    assert pacote["strategy"] == "baseline" and pacote["evidence"][0]["sistema"] == "SIS-01"
