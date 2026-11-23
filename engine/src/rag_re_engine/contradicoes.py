"""Julgamento de contradições entre requisitos por LLM.

`recop.py pares` só pega contradições com sinal léxico (polaridade, números). As de sentido — "pago na folha"
contra "pago por PIX em 2 dias" — passam. Aqui o LLM lê os pares do mesmo tema (`pares --amplo`) em lotes e
classifica cada um. O resultado é sugestão: quem registra `rel.conflita_com` é o agente, depois de conferir.
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

Pares:
{pares}

Responda só com JSON: [{{"par": <número>, "classe": "contradicao|complementar|independente", "motivo": "<uma frase>"}}]"""


def julgar(pares: list[dict], llm: LLM, lote: int = 8) -> dict:
    """Classifica pares `{a, b, enunciado_a, enunciado_b}`. Lote que falha vira aviso, sem derrubar o resto."""
    resultado = {"avaliados": 0, "contradicoes": [], "complementares": [], "avisos": [], "llm": llm.name}
    for inicio in range(0, len(pares), lote):
        grupo = pares[inicio : inicio + lote]
        texto = "\n".join(f"{i}. [{p['a']}] {p['enunciado_a']}\n   [{p['b']}] {p['enunciado_b']}"
                          for i, p in enumerate(grupo, 1))
        try:
            respostas = parse_json(llm.complete(PROMPT.format(pares=texto)))
        except (RuntimeError, ValueError) as exc:
            resultado["avisos"].append(f"lote {inicio // lote + 1}: {exc}")
            continue
        for r in respostas if isinstance(respostas, list) else []:
            try:
                par = grupo[int(r["par"]) - 1]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            classe = str(r.get("classe", "")).strip().lower().replace("ç", "c").replace("ã", "a")
            if classe not in CLASSES:
                continue
            resultado["avaliados"] += 1
            item = {"a": par["a"], "b": par["b"], "motivo": r.get("motivo", ""), "sinais": par.get("sinais", [])}
            if classe == "contradicao":
                resultado["contradicoes"].append(item)
            elif classe == "complementar":
                resultado["complementares"].append(item)
    return resultado
