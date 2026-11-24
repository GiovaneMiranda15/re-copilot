"""Mede a detecção de contradições: candidatos, regra léxica e julgamento por LLM.

    uv run --project <re-copilot> python engine/benchmarks/contradicoes.py --llm ollama --saida relatorio.json

Os pares foram escritos e rotulados pelo autor da ferramenta: servem para achar regressão e comparar modelos, não como
evidência independente de qualidade. `C` contradição, `S` complementar (se somam), `I` independente. `armadilha` marca os
que parecem contradição e não são (perfis, casos ou etapas diferentes).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from rag_re_engine import operacoes
from rag_re_engine.contradicoes import julgar
from rag_re_engine.llm import get_llm

PARES = [
    # Contradição com sinal na superfície (número, negação, exclusividade)
    ("C", "", "O pedido cancelado deve ser estornado em até 5 dias.", "O pedido cancelado deve ser estornado em até 30 dias."),
    ("C", "", "O vendedor pode alterar o preço do item.", "O vendedor não pode alterar o preço do item."),
    ("C", "", "Somente o diretor aprova desconto acima de 20%.", "O gerente aprova desconto acima de 20%."),
    ("C", "", "A senha deve ter no mínimo 12 caracteres.", "A senha deve ter no máximo 8 caracteres."),
    ("C", "", "O sistema deve bloquear o cliente após 2 parcelas vencidas.", "O sistema deve bloquear o cliente após 4 parcelas vencidas."),
    ("C", "", "O cupom é cumulativo com outras promoções.", "O cupom não é cumulativo com outras promoções."),
    # Contradição de sentido
    ("C", "", "O reembolso é creditado na folha do mês seguinte.", "O reembolso é pago por PIX em dois dias úteis."),
    ("C", "", "O cadastro do paciente é excluído a pedido do titular.", "O cadastro do paciente é mantido permanentemente para auditoria."),
    ("C", "", "A matrícula só é confirmada depois da compensação do boleto.", "A matrícula é confirmada no envio da proposta assinada."),
    ("C", "", "O estoque é baixado na separação do pedido.", "O estoque é baixado na emissão da nota fiscal do pedido."),
    ("C", "", "O entregador vê apenas o bairro do destinatário.", "O aplicativo mostra ao entregador o endereço completo do destinatário."),
    ("C", "", "Toda compra passa por cotação com três fornecedores.", "Compras recorrentes são emitidas direto ao fornecedor homologado."),
    ("C", "", "O aplicativo funciona sem conexão durante a visita.", "Cada resposta da visita é validada em tempo real no servidor."),
    ("C", "", "O acesso ao painel usa a conta corporativa, sem senha própria.", "O usuário do painel define uma senha no primeiro acesso."),
    ("C", "", "A comissão é calculada sobre o valor faturado.", "A comissão é calculada sobre o valor recebido."),
    ("C", "", "O laudo é liberado automaticamente quando o exame termina.", "Nenhum laudo chega ao paciente sem assinatura do médico."),
    # Complementares, com armadilhas
    ("S", "", "O gerente aprova o reembolso.", "O reembolso aprovado gera lançamento contábil."),
    ("S", "armadilha", "Reembolso até R$ 800 é aprovado pelo gerente.", "Reembolso acima de R$ 800 é aprovado pelo diretor."),
    ("S", "armadilha", "Cliente pessoa física paga em até 6 parcelas.", "Cliente pessoa jurídica paga em até 12 parcelas."),
    ("S", "armadilha", "O vendedor não pode excluir pedidos.", "O administrador pode excluir pedidos."),
    ("S", "armadilha", "O log de acesso é guardado por 6 meses.", "A nota fiscal é guardada por 5 anos."),
    ("S", "armadilha", "O pedido em rascunho pode ser editado.", "O pedido faturado não pode ser editado."),
    ("S", "", "O boleto é enviado por e-mail.", "O boleto pode ser baixado no portal do cliente."),
    ("S", "armadilha", "O prazo de resposta do chamado crítico é de 1 hora.", "O prazo de resposta do chamado comum é de 8 horas."),
    ("S", "", "O sistema registra quem alterou o preço.", "O histórico de alteração de preço é exibido ao auditor."),
    ("S", "armadilha", "A busca responde em até 2 segundos para 95% das consultas.", "A exportação da busca pode levar até 60 segundos."),
    ("S", "armadilha", "O plantão noturno é cumprido por dois enfermeiros.", "O plantão diurno é cumprido por quatro enfermeiros."),
    ("S", "armadilha", "O desconto máximo é de 10%.", "Com autorização do diretor, o desconto pode passar de 10%."),
    # Independentes com palavras em comum
    ("I", "", "O relatório de vendas é exportado em planilha.", "O relatório de férias é assinado pelo RH."),
    ("I", "armadilha", "O prazo de entrega do pedido é de 5 dias.", "O prazo de validade do orçamento é de 15 dias."),
    ("I", "armadilha", "O contrato do fornecedor vence em 12 meses.", "O contrato de trabalho temporário vence em 6 meses."),
    ("I", "", "O cliente recebe aviso de pagamento.", "O fornecedor recebe aviso de vaga no pátio."),
    ("I", "armadilha", "O código do produto tem 13 dígitos.", "O código do cliente tem 8 dígitos."),
    ("I", "", "A tela de login mostra o logotipo da filial.", "A tela de estoque mostra o saldo da filial."),
    ("I", "armadilha", "O arquivo de retorno do banco é importado às 6h.", "O arquivo de folha é enviado às 18h."),
    ("I", "", "O médico consulta a agenda da semana.", "O paciente consulta o resultado do exame."),
]


def metricas(previstos: set[int]) -> dict:
    reais = {i for i, p in enumerate(PARES) if p[0] == "C"}
    vp = len(previstos & reais)
    precisao = vp / len(previstos) if previstos else 0.0
    recall = vp / len(reais)
    f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
    return {"contradicoes_reais": len(reais), "apontadas": len(previstos), "corretas": vp, "precisao": round(precisao, 3),
            "recall": round(recall, 3), "f1": round(f1, 3),
            "recall_superficie": round(len(previstos & set(range(6))) / 6, 3),
            "recall_sentido": round(len(previstos & set(range(6, 16))) / 10, 3),
            "armadilhas_falsas": len({i for i in previstos if PARES[i][1] == "armadilha"}),
            "falsos": [PARES[i][2:] for i in sorted(previstos - reais)],
            "perdidas": [PARES[i][2:] for i in sorted(reais - previstos)]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="append", default=[], help="repita para comparar modelos (ex.: ollama, claude:haiku)")
    ap.add_argument("--lote", type=int, default=8)
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args()
    r = operacoes.recop()
    itens = [{"id": f"RF-{2 * i + j:03d}", "titulo": "", "enunciado": texto, "status": "hipótese"}
             for i, par in enumerate(PARES) for j, texto in enumerate(par[2:], 1)]
    modelo = {nome: [] for nome in r.COLLECTIONS} | {"requisitos": itens}
    indice = {(f"RF-{2 * i + 1:03d}", f"RF-{2 * i + 2:03d}"): i for i in range(len(PARES))}
    reais = [k for k, i in indice.items() if PARES[i][0] == "C"]

    amplos = [(p["a"], p["b"]) for p in r.pares_amplos(modelo, 0)]
    rel = {"pares": len(PARES), "armadilhas": sum(1 for p in PARES if p[1]), "autoria": "autor da ferramenta",
           "candidatos_no_projeto_inteiro": {"pares_possiveis": len(itens) * (len(itens) - 1) // 2, "candidatos": len(amplos)}
           | {f"recall_{'todos' if not n else f'top{n}'}": round(sum(k in set(amplos[:n or None]) for k in reais) / len(reais), 3)
              for n in (60, 120, 0)}}
    lexicos = {indice[k] for p in r.pares_revisar(modelo, limite=10_000, por_regra_max=10_000) for k in [(p["a"], p["b"])] if k in indice}
    rel["lexico (recop.py pares)"] = metricas(lexicos)
    entrada = [{"a": a, "b": b, "enunciado_a": PARES[i][2], "enunciado_b": PARES[i][3]} for (a, b), i in indice.items()]
    ordem = sorted(range(len(entrada)), key=lambda i: (i * 17) % len(entrada))  # embaralha: classes não ficam em bloco
    for spec in args.llm:
        t0 = time.perf_counter()
        j = julgar([entrada[i] for i in ordem], get_llm(spec), args.lote)
        rel[f"llm {spec}"] = metricas({indice[(c["a"], c["b"])] for c in j["contradicoes"]}) | {
            "julgados": j["avaliados"], "sem_resposta": len(j["sem_resposta"]), "segundos": round(time.perf_counter() - t0, 1),
            "avisos": j["avisos"]}
    texto = json.dumps(rel, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.write_text(texto + "\n")
    print(texto)


if __name__ == "__main__":
    main()
