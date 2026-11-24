"""Operações de alto nível do motor, compartilhadas pela CLI e pelo servidor MCP."""

from __future__ import annotations

import sys
from pathlib import Path

from rag_re_engine.contradicoes import julgar
from rag_re_engine.embeddings import get_embedder
from rag_re_engine.engine import retrieve
from rag_re_engine.ingest import chunk_text, load_documents
from rag_re_engine.llm import LLM, get_llm
from rag_re_engine.models import EvidencePackage
from rag_re_engine.pipelines.graph import build_graph
from rag_re_engine.pipelines.raptor import build_raptor
from rag_re_engine.skill_files import pasta_skill, recop  # noqa: F401
from rag_re_engine.store import SqliteStore

DEFAULT_EMBEDDER = "fastembed:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# Formatos que o motor não lê direto: `recop.py extrair` transcreve para .re/extraidos, que é indexável.
PARA_EXTRAIR = {".docx", ".pptx", ".xlsx", ".xlsm"}


def resolver_llm(spec: str | None, avisos: list[str] | None = None) -> LLM | None:
    """`none` desliga o LLM. Se `auto` não achar provedor, segue sem LLM e registra o aviso."""
    if not spec or spec == "none":
        return None
    try:
        return get_llm(spec)
    except RuntimeError as exc:
        if avisos is not None:
            avisos.append(str(exc))
        else:
            print(f"aviso: {exc}", file=sys.stderr)
        return None


def abrir_indice(db: Path, sistemas: set[str] | None = None):
    if not Path(db).exists():
        raise FileNotFoundError(f"índice não encontrado: {db} (rode `index` antes)")
    store = SqliteStore(db, sistemas)
    if not store.embedder_name:
        raise ValueError(f"índice vazio: {db}")
    return store, get_embedder(store.embedder_name)


def indexar(pasta: Path, db: Path, sistema: str = "", tipo: str | None = None, embedder: str = DEFAULT_EMBEDDER,
            max_chars: int = 1200, overlap: int = 200) -> dict:
    emb = get_embedder(embedder)
    prefixo = f"{sistema}/" if sistema else ""
    docs = {f"{prefixo}{doc_id}": texto for doc_id, texto in load_documents(Path(pasta)).items()}
    chunks = [c for doc_id, texto in docs.items()
              for c in chunk_text(doc_id, texto, max_chars, overlap, sistema=sistema, tipo=tipo)]
    extrair = sorted(str(p.relative_to(pasta)) for p in Path(pasta).rglob("*") if p.suffix.lower() in PARA_EXTRAIR)
    aviso_extrair = (f"{len(extrair)} arquivo(s) não indexado(s) ({', '.join(extrair[:5])}"
                     f"{' …' if len(extrair) > 5 else ''}): rode `recop.py extrair <arquivo>` e indexe .re/extraidos")
    if not chunks:
        return {"documentos": 0, "chunks": 0,
                "aviso": aviso_extrair if extrair else f"nenhum documento suportado em {pasta}"}
    store = SqliteStore(db)
    store.delete_docs(list(docs))
    for i in range(0, len(chunks), 64):
        parte = chunks[i : i + 64]
        store.add(parte, emb.embed([c.text for c in parte]), emb.name)
    rel = {"documentos": len(docs), "chunks": len(chunks), "embedder": emb.name, "db": str(db)}
    if extrair:
        rel["aviso"] = aviso_extrair
    return rel


def buscar(db: Path, atividade: str, consulta: str, k: int = 5, sistemas: set[str] | None = None,
           llm: str | None = "auto", estrategia: str | None = None) -> EvidencePackage:
    avisos: list[str] = []
    store, emb = abrir_indice(db, sistemas)
    pacote = retrieve(consulta, atividade, store, emb, resolver_llm(llm, avisos), k=k, strategy=estrategia)
    pacote.notes = avisos + pacote.notes
    return pacote


def construir(db: Path, o_que: set[str], llm: str = "auto") -> dict:
    avisos: list[str] = []
    modelo = resolver_llm(llm, avisos)
    if modelo is None:
        raise RuntimeError("`build` precisa de um LLM: " + ("; ".join(avisos) or "use --llm"))
    store, emb = abrir_indice(db)
    relatorio: dict = {}
    if "raptor" in o_que:
        relatorio["raptor"] = build_raptor(store, emb, modelo)
    if "graph" in o_que:
        relatorio["graph"] = build_graph(store, emb, modelo)
    return relatorio


def contradicoes(re_dir: Path, llm: str = "auto", n: int = 60, lote: int = 8) -> dict:
    """Julga por LLM os `n` pares do mesmo tema mais fortes (`recop.py pares --amplo`); `n` ≤ 0 julga todos.

    `cobertura` diz o que ficou de fora: pares cortados pelo limite, já ligados ou sem palavra em comum.
    """
    avisos: list[str] = []
    modelo = resolver_llm(llm, avisos)
    if modelo is None:
        raise RuntimeError("`contradicoes` precisa de um LLM: " + ("; ".join(avisos) or "use --llm")
                           + ". Sem LLM, leia `recop.py pares --amplo` e julgue os pares você mesmo.")
    r = recop()
    dados = r.load(Path(re_dir))
    candidatos = r.pares_amplos(dados, 0)
    pares = candidatos[:n] if n > 0 else candidatos
    ativos = sum(1 for x in dados["requisitos"] if x.get("status") not in {"descartado", "obsoleto"})
    resultado = julgar(pares, modelo, lote)
    if pares and not resultado["avaliados"]:  # "nenhuma contradição" aqui seria mentira
        raise RuntimeError(f"nenhum par foi julgado por {modelo.name}: " + "; ".join(dict.fromkeys(resultado["avisos"]))[:400])
    possiveis = ativos * (ativos - 1) // 2
    cortados = len(candidatos) - len(pares)
    resultado["cobertura"] = {"pares_possiveis": possiveis, "ligados_ou_sem_termo_comum": possiveis - len(candidatos),
                              "candidatos": len(candidatos), "enviados": len(pares), "cortados_pelo_limite": cortados}
    if cortados:
        resultado["completo"] = False
        resultado["avisos"].append(f"{cortados} par(es) candidato(s) não foram julgados (limite n={n}). Use -n 0 para julgar todos.")
    resultado["pares"] = len(pares)
    return resultado
