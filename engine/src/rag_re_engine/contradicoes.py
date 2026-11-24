"""Julgamento de contradições entre requisitos por LLM.

`recop.py pares` só pega contradições com sinal léxico (polaridade, números). As de sentido — "pago na folha"
contra "pago por PIX em 2 dias" — passam. Aqui o LLM lê os pares do mesmo tema (`pares --amplo`) em lotes e
classifica cada um. O resultado é sugestão: quem registra `rel.conflita_com` é o agente, depois de conferir.

Nenhum par some em silêncio: o que o LLM não responde (ou responde fora do formato) é repetido uma vez em lotes
menores; se ainda faltar, sai em `sem_resposta` e o resultado vem com `completo: false`.
"""

from __future__ import annotations

from rag_re_engine.llm import LLM, parse_json

CLASSES = {"contradicao", "complementar", "independente"}

PROMPT = """Você revisa requisitos de software em busca de contradições.
Para cada par abaixo, decida:
- "contradicao": os dois não podem valer ao mesmo tempo no mesmo sistema (regras, valores, prazos, canais ou responsáveis incompatíveis);
- "complementar": tratam do mesmo assunto e se somam sem conflito;
- "independente": assuntos diferentes, apesar de palavras em comum.
Não invente contexto. Se só houver conflito sob uma interpretação, use "contradicao" e explique qual.
Regras para casos, perfis, sistemas ou etapas diferentes não se contradizem só por terem valores diferentes.

Pares:
{pares}

Responda só com JSON, um objeto para cada par, todos os {total}:
[{{"par": <número>, "classe": "contradicao|complementar|independente", "motivo": "<uma frase>"}}]"""


def _lote(grupo: list[dict], llm: LLM) -> dict[int, tuple[str, str]]:
    """Respostas válidas do lote: posição → (classe, motivo). Resposta repetida e divergente conta como ausente."""
    texto = "\n".join(f"{i}. [{p['a']}] {p['enunciado_a']}\n   [{p['b']}] {p['enunciado_b']}" for i, p in enumerate(grupo, 1))
    respostas = parse_json(llm.complete(PROMPT.format(pares=texto, total=len(grupo))))
    if isinstance(respostas, dict):  # alguns modelos embrulham a lista, ou respondem o objeto único
        respostas = next((v for v in respostas.values() if isinstance(v, list)), [respostas])
    validas: dict[int, tuple[str, str]] = {}
    ambiguas: set[int] = set()
    for r in respostas if isinstance(respostas, list) else []:
        try:
            pos = int(r["par"]) - 1
            classe = str(r["classe"]).strip().lower().replace("ç", "c").replace("ã", "a")
        except (KeyError, ValueError, TypeError):
            continue
        if not 0 <= pos < len(grupo) or classe not in CLASSES:
            continue
        if pos in validas and validas[pos][0] != classe:
            ambiguas.add(pos)
        validas.setdefault(pos, (classe, str(r.get("motivo") or "")))
    return {pos: v for pos, v in validas.items() if pos not in ambiguas}


def julgar(pares: list[dict], llm: LLM, lote: int = 8) -> dict:
    """Classifica pares `{a, b, enunciado_a, enunciado_b}`. Lote que falha vira aviso, sem derrubar o resto."""
    lote = max(1, lote)
    julgados: dict[int, tuple[str, str]] = {}
    avisos: list[str] = []
    pendentes = list(range(len(pares)))
    for rodada, tamanho in enumerate((lote, max(1, lote // 2)), 1):
        for inicio in range(0, len(pendentes), tamanho):
            indices = pendentes[inicio : inicio + tamanho]
            try:
                respostas = _lote([pares[i] for i in indices], llm)
            except (RuntimeError, ValueError) as exc:
                avisos.append(f"rodada {rodada}, lote {inicio // tamanho + 1}: {exc}")
                continue
            julgados |= {indices[pos]: v for pos, v in respostas.items()}
        pendentes = [i for i in pendentes if i not in julgados]
        if not pendentes:
            break

    resultado = {"llm": llm.name, "avaliados": len(julgados), "completo": not pendentes, "contradicoes": [], "complementares": [],
                 "sem_resposta": [{"a": pares[i]["a"], "b": pares[i]["b"]} for i in pendentes], "avisos": avisos}
    for i, (classe, motivo) in sorted(julgados.items()):
        item = {"a": pares[i]["a"], "b": pares[i]["b"], "motivo": motivo, "sinais": pares[i].get("sinais", [])}
        if classe == "contradicao":
            resultado["contradicoes"].append(item)
        elif classe == "complementar":
            resultado["complementares"].append(item)
    if pendentes:
        avisos.append(f"{len(pendentes)} par(es) sem julgamento: leia-os em `sem_resposta` ou rode de novo.")
    return resultado
