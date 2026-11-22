"""Servidor MCP do re-copilot: leva o método e as ferramentas a qualquer cliente MCP (Claude, Cursor, Codex, etc.).

Expõe:
- o prompt `re-copilot`, com as instruções da skill (SKILL.md), e cada referência e perfil como recurso;
- as ferramentas do `recop.py` (modelo, checagens, rastreabilidade, baseline, exportação, leitura segura);
- as ferramentas do motor RAG (indexar, buscar, construir).

`projeto` é sempre a pasta do projeto analisado, onde fica `.re/`. Uso: `re-copilot-mcp` (stdio).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from rag_re_engine import operacoes


def _pasta_skill() -> Path:
    """No repositório, a raiz; instalado como pacote, a cópia em `rag_re_engine/skill`."""
    empacotada = Path(__file__).resolve().parent / "skill"
    if (empacotada / "SKILL.md").exists():
        return empacotada
    return Path(__file__).resolve().parents[3]


def _recop():
    try:
        import recop
    except ImportError:
        sys.path.insert(0, str(_pasta_skill() / "scripts"))
        import recop
    return recop


SKILL = _pasta_skill()
INSTRUCOES = (
    "Copiloto de Engenharia de Requisitos. Antes de agir, leia o prompt `re-copilot` (ou o recurso re-copilot://skill) "
    "e siga o método. As ferramentas `re_*` operam sobre `<projeto>/.re`; as `rag_*`, sobre o índice do motor."
)
mcp = MCPServer("re-copilot", instructions=INSTRUCOES)


def _re(projeto: str) -> Path:
    return Path(projeto).expanduser().resolve() / ".re"


def _carregar(projeto: str):
    re_dir = _re(projeto)
    if not re_dir.is_dir():
        raise ToolError(f"{re_dir} não existe: rode `re_init` antes")
    return re_dir, _recop().load(re_dir)


def _executar(funcao):
    """O recop sinaliza recusas com SystemExit; no MCP isso vira ToolError, cuja mensagem chega ao cliente."""
    try:
        return funcao()
    except SystemExit as exc:
        raise ToolError(str(exc)) from exc


# ------------------------------------------------------------------ instruções

@mcp.prompt(name="re-copilot", description="Método completo do re-copilot (SKILL.md) e onde ler cada referência.")
def prompt_skill() -> str:
    return (SKILL / "SKILL.md").read_text() + (
        "\n\n---\nNeste ambiente, `<skill>` são recursos MCP: re-copilot://references/<arquivo> e "
        "re-copilot://roles/<perfil>. Os comandos `recop.py` estão disponíveis como ferramentas `re_*`.")


@mcp.resource("re-copilot://skill", name="SKILL.md", mime_type="text/markdown")
def recurso_skill() -> str:
    return (SKILL / "SKILL.md").read_text()


@mcp.resource("re-copilot://references/{arquivo}", name="Referência", mime_type="text/markdown")
def recurso_referencia(arquivo: str) -> str:
    return _arquivo_seguro(SKILL / "references", arquivo)


@mcp.resource("re-copilot://roles/{perfil}", name="Perfil", mime_type="text/markdown")
def recurso_perfil(perfil: str) -> str:
    return _arquivo_seguro(SKILL / "roles", perfil if perfil.endswith(".md") else f"{perfil}.md")


def _arquivo_seguro(pasta: Path, nome: str) -> str:
    caminho = (pasta / nome).resolve()
    if caminho.parent != pasta.resolve() or not caminho.is_file():
        raise ValueError(f"não encontrado: {nome}")
    return caminho.read_text()


@mcp.tool(description="Lista as referências e os perfis disponíveis do método.")
def re_indice() -> dict:
    return {"referencias": sorted(p.name for p in (SKILL / "references").glob("*.md")),
            "perfis": sorted(p.stem for p in (SKILL / "roles").glob("*.md"))}


# ------------------------------------------------------------------ modelo (recop)

@mcp.tool(description="Cria o esqueleto de <projeto>/.re sem sobrescrever nada.")
def re_init(projeto: str, nome: str) -> list[str]:
    return _recop().init_projeto(_re(projeto), nome)


@mcp.tool(description="Painel: fase, contagens de requisitos, achados, perguntas, backlog e mudanças.")
def re_status(projeto: str) -> dict:
    re_dir, model = _carregar(projeto)
    return _recop().status(re_dir, model)


@mcp.tool(description="Integridade do modelo: IDs, status e referências. Lista vazia = ok.")
def re_check(projeto: str) -> list[str]:
    return _recop().check(_carregar(projeto)[1])


@mcp.tool(description="Lacunas de completude: critérios, cobertura, confirmados com pergunta aberta, fontes sem item.")
def re_lint(projeto: str) -> dict:
    re_dir, model = _carregar(projeto)
    return _recop().lint(model, re_dir)


@mcp.tool(description="Confere contra as fontes: números sem fonte, confirmado sem autoridade, citações, dados sensíveis. "
                      "`docs` é a pasta de entregáveis (relativa ao projeto), opcional.")
def re_verificar(projeto: str, docs: str | None = None) -> dict:
    re_dir, model = _carregar(projeto)
    pasta = (Path(projeto).expanduser() / docs) if docs else None
    return _recop().verificar(re_dir, model, pasta)


@mcp.tool(description="Gera as visões .md (requisitos, achados, backlog, rastreabilidade, cenários) a partir do modelo.")
def re_render(projeto: str) -> list[str]:
    re_dir, model = _carregar(projeto)
    return [str(p) for p in _recop().render(re_dir, model)]


@mcp.tool(description="Fontes novas, alteradas e removidas desde o último registro. `atualizar` grava os hashes.")
def re_fontes(projeto: str, atualizar: bool = False) -> dict:
    return _recop().scan_fontes(_re(projeto), atualizar)


@mcp.tool(description="Itens afetados por uma mudança nos IDs dados, percorrendo o grafo de requisitos.")
def re_impacto(projeto: str, ids: list[str], profundidade: int = 3) -> dict:
    return _executar(lambda: _recop().impacto_multi(_carregar(projeto)[1], ids, profundidade))


@mcp.tool(description="Itens do modelo com termos em comum com uma afirmação nova (entrada do classificador).")
def re_candidatos(projeto: str, texto: str, n: int = 8) -> list[dict]:
    return _recop().candidatos(_carregar(projeto)[1], texto, n)


@mcp.tool(description="Pares de requisitos a revisar por possível contradição.")
def re_pares(projeto: str) -> list[dict]:
    return _recop().pares_revisar(_carregar(projeto)[1])


@mcp.tool(description="Notas e arquivos citados nas fontes e ainda não registrados.")
def re_ligacoes(projeto: str) -> list[dict]:
    re_dir, model = _carregar(projeto)
    return _recop().ligacoes(re_dir, model)


@mcp.tool(description="Congela requisitos e backlog numa baseline. Recusa com modelo inconsistente ou conflito aberto.")
def re_baseline(projeto: str, nota: str = "") -> dict:
    re_dir, model = _carregar(projeto)
    return _executar(lambda: _recop().criar_baseline(re_dir, model, nota))


@mcp.tool(description="O que foi criado, removido e alterado desde a baseline (a vigente, se omitida).")
def re_diff(projeto: str, baseline: str | None = None) -> dict:
    re_dir, model = _carregar(projeto)
    return _executar(lambda: _recop().diff_baseline(re_dir, model, baseline))


@mcp.tool(description="Exporta o backlog em CSV para `jira` ou `azure` (processo agile, scrum ou basic). "
                      "Com `saida`, grava no arquivo (relativo ao projeto); sem ela, devolve o texto.")
def re_exportar(projeto: str, destino: str, processo: str = "agile", delta: bool = False, saida: str | None = None) -> str:
    model = _carregar(projeto)[1]
    r = _recop()
    texto = _executar(lambda: r.export_jira(model, delta) if destino == "jira" else r.export_azure(model, processo, delta))
    if saida:
        caminho = Path(projeto).expanduser() / saida
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto)
        return f"gerado {caminho}"
    return texto


@mcp.tool(description="Lê um arquivo ocultando tokens, senhas e CPF; recusa arquivos de credenciais. "
                      "`linhas` no formato '10-40'.")
def re_ler_arquivo(caminho: str, linhas: str | None = None) -> str:
    return _executar(lambda: _recop().ver_arquivo(Path(caminho).expanduser(), linhas))


# ------------------------------------------------------------------ motor RAG

def _db(projeto: str) -> Path:
    return _re(projeto) / "index.db"


@mcp.tool(description="Indexa uma pasta de fontes no índice do projeto (.re/index.db), marcando o sistema de origem.")
def rag_indexar(projeto: str, pasta: str, sistema: str = "", embedder: str = operacoes.DEFAULT_EMBEDDER) -> dict:
    _re(projeto).mkdir(parents=True, exist_ok=True)
    return operacoes.indexar(Path(pasta).expanduser(), _db(projeto), sistema, None, embedder)


@mcp.tool(description="Busca evidências com a arquitetura RAG da atividade (elicitacao, analise, especificacao, validacao, "
                      "gerenciamento_mudancas, rastreabilidade). `llm`: auto, claude, anthropic, openai, ollama ou none.")
def rag_buscar(projeto: str, atividade: str, consulta: str, k: int = 5, sistemas: list[str] | None = None,
               llm: str = "auto") -> dict:
    return operacoes.buscar(_db(projeto), atividade, consulta, k, set(sistemas) if sistemas else None, llm).to_dict()


@mcp.tool(description="Constrói as estruturas que usam LLM: árvore RAPTOR e grafo do GraphRAG (`o_que`: raptor, graph).")
def rag_construir(projeto: str, o_que: list[str] | None = None, llm: str = "auto") -> dict:
    return operacoes.construir(_db(projeto), set(o_que or ["raptor", "graph"]), llm)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
