"""Julgamento de contradições por LLM (com LLM falso) e aviso de formatos a extrair na indexação."""

from __future__ import annotations

import json
from pathlib import Path

from rag_re_engine import operacoes
from rag_re_engine.contradicoes import julgar


class LLMFalso:
    name = "falso"

    def __init__(self, respostas: list[str]) -> None:
        self.respostas = respostas
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        resposta = self.respostas.pop(0)
        if resposta == "erro":
            raise RuntimeError("limite de uso")
        return resposta


PARES = [{"a": f"RN-{i:03d}", "b": f"RF-{i:03d}", "enunciado_a": "x", "enunciado_b": "y"} for i in range(1, 4)]


def test_julgar_classifica_e_ignora_lixo() -> None:
    llm = LLMFalso(['```json\n[{"par": 1, "classe": "contradição", "motivo": "folha × PIX"},'
                    ' {"par": 2, "classe": "complementar"}, {"par": 9, "classe": "contradicao"},'
                    ' {"par": 3, "classe": "talvez"}]\n```'])
    rel = julgar(PARES, llm)
    assert rel["avaliados"] == 2
    assert rel["contradicoes"] == [{"a": "RN-001", "b": "RF-001", "motivo": "folha × PIX", "sinais": []}]
    assert [c["a"] for c in rel["complementares"]] == ["RN-002"]
    assert "[RN-001] x" in llm.prompts[0]


def test_julgar_lote_com_falha_vira_aviso() -> None:
    rel = julgar(PARES, LLMFalso(["erro", '[{"par": 1, "classe": "contradicao"}]']), lote=2)
    assert rel["avisos"] and rel["contradicoes"][0]["a"] == "RN-003"


def test_contradicoes_de_ponta_a_ponta(tmp_path: Path, monkeypatch) -> None:
    r = operacoes.recop()
    r.init_projeto(tmp_path / ".re", "x")
    (tmp_path / ".re" / "modelo" / "requisitos.json").write_text(json.dumps({"itens": [
        {"id": "RN-001", "enunciado": "Reembolso pago na folha do mês seguinte.", "status": "hipótese"},
        {"id": "RF-001", "enunciado": "Reembolso pago por PIX em 2 dias.", "status": "hipótese"}]}))
    monkeypatch.setattr(operacoes, "get_llm", lambda spec: LLMFalso(['[{"par": 1, "classe": "contradicao", "motivo": "m"}]']))
    rel = operacoes.contradicoes(tmp_path / ".re", "falso")
    assert rel["pares"] == 1 and rel["contradicoes"][0]["b"] == "RF-001"


def test_indexar_avisa_formatos_para_extrair(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("Política de reembolso.")
    (tmp_path / "docs" / "b.docx").write_bytes(b"PK")
    rel = operacoes.indexar(tmp_path / "docs", tmp_path / "i.db", embedder="hash")
    assert rel["chunks"] == 1 and "b.docx" in rel["aviso"] and "recop.py extrair" in rel["aviso"]
