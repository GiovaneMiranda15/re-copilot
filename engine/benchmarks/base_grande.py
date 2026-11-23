"""Teste de escala do motor: corpus sintético com fatos plantados.

Gera N documentos de M sistemas (texto de domínio parecido entre si, para dificultar), planta um fato único por
documento e mede indexação, tamanho do índice, latência de busca e recall@k (o documento do fato está no top-k?).

    uv run --project <re-copilot> --extra embeddings python engine/benchmarks/base_grande.py --docs 600 --saida <pasta>

Sem LLM: compara a busca só vetorial (densa) com a híbrida (vetorial + BM25). Pipelines com LLM custam uma chamada por consulta e
ficam para `rag-re-engine evaluate` numa amostra.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import time
from pathlib import Path

from rag_re_engine import operacoes

AREAS = ["vendas", "financeiro", "estoque", "cobrança", "atendimento", "logística"]
SUJEITOS = ["o pedido", "a nota fiscal", "o boleto", "o cadastro do cliente", "a devolução", "o contrato", "a comissão",
            "o reembolso", "a ordem de compra", "o título a receber", "a entrega", "o chamado"]
VERBOS = ["é validado", "é aprovado", "é registrado", "é conferido", "é enviado", "é conciliado", "é reprocessado",
          "é bloqueado", "é liberado", "é arquivado"]
QUANDO = ["no fechamento do dia", "antes da emissão", "após a confirmação do pagamento", "quando o gerente aprova",
          "na integração noturna", "a cada lote de 50 itens", "no primeiro acesso", "ao final do mês"]
QUEM = ["pelo supervisor", "pelo sistema legado", "pela equipe de backoffice", "pelo analista fiscal",
        "pelo operador da filial", "automaticamente", "pela central", "pelo coordenador regional"]
OBJETOS = ["filial", "regional", "carteira", "rota", "loja", "centro de distribuição"]


def frase(rnd: random.Random) -> str:
    return f"{rnd.choice(SUJEITOS).capitalize()} {rnd.choice(VERBOS)} {rnd.choice(QUANDO)} {rnd.choice(QUEM)}."


def gerar(pasta: Path, n_docs: int, semente: int = 7) -> list[dict]:
    rnd = random.Random(semente)
    consultas = []
    for i in range(n_docs):
        area = AREAS[i % len(AREAS)]
        sistema = f"SIS-{i % len(AREAS) + 1:02d}"
        objeto = rnd.choice(OBJETOS)
        numero = 100 + i
        valor = rnd.randint(2, 98) * 50
        prazo = rnd.randint(2, 45)
        fato = (f"Na {objeto} {numero}, o limite de aprovação de {area} é de R$ {valor} e o prazo de retenção "
                f"dos comprovantes é de {prazo} dias.")
        paragrafos = [" ".join(frase(rnd) for _ in range(5)) for _ in range(6)]
        paragrafos.insert(rnd.randint(1, 5), fato + " " + frase(rnd))
        destino = pasta / sistema / f"{area}-{i:04d}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(f"# Procedimento de {area} {i:04d}\n\n" + "\n\n".join(paragrafos) + "\n")
        consultas.append({"sistema": sistema, "doc": f"{sistema}/{destino.name}",
                          "consulta": f"Qual o limite de aprovação de {area} na {objeto} {numero}?"})
    return consultas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=600)
    ap.add_argument("--consultas", type=int, default=100)
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--embedder", default=operacoes.DEFAULT_EMBEDDER)
    ap.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args()
    corpus, db = args.saida / "corpus", args.saida / "index.db"
    if db.exists():
        db.unlink()
    consultas = gerar(corpus, args.docs)

    inicio = time.perf_counter()
    chunks = 0
    for sistema in sorted(p.name for p in corpus.iterdir()):
        chunks += operacoes.indexar(corpus / sistema, db, sistema, None, args.embedder)["chunks"]
    t_index = time.perf_counter() - inicio

    amostra = random.Random(1).sample(consultas, min(args.consultas, len(consultas)))
    resultados = {}
    for modo, estrategia in (("densa", "baseline"), ("hibrida", "baseline"), ("hibrida", "corrective_rag")):
        os.environ["RAG_RE_BUSCA"] = modo
        latencias, acertos, rr = [], 0, 0.0
        for q in amostra:
            t0 = time.perf_counter()
            pacote = operacoes.buscar(db, "analise", q["consulta"], args.k, None, "none", estrategia)
            latencias.append(time.perf_counter() - t0)
            docs = [e.chunk_id.split("#")[0] for e in pacote.evidence]
            if q["doc"] in docs:
                acertos += 1
                rr += 1 / (docs.index(q["doc"]) + 1)
        resultados[f"{estrategia} ({modo})"] = {"recall_at_k": round(acertos / len(amostra), 3), "mrr": round(rr / len(amostra), 3),
                                  "latencia_media_s": round(statistics.mean(latencias), 3),
                                  "latencia_p95_s": round(sorted(latencias)[int(0.95 * len(latencias)) - 1], 3)}
    relatorio = {"documentos": args.docs, "chunks": chunks, "embedder": args.embedder,
                 "indexacao_s": round(t_index, 1), "chunks_por_s": round(chunks / t_index, 1),
                 "indice_mb": round(db.stat().st_size / 2**20, 1), "consultas": len(amostra), "k": args.k,
                 "estrategias": resultados}
    (args.saida / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2))
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
