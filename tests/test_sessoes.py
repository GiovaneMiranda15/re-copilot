"""Manutenção entre sessões: cada etapa é um processo novo do recop.py, só com o que ficou em `.re/`.

Simula voltar ao projeto dias depois: a fonte muda, o hook de início de sessão avisa, o agente aplica o CR,
a baseline nova registra a diferença e só o que mudou vai para o backlog.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recop.py"


def recop(raiz: Path, *args: str, ok: bool = True) -> str:
    proc = subprocess.run([sys.executable, "-I", str(SCRIPT), *args], cwd=raiz, capture_output=True, text=True)
    if ok:
        assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def gravar(raiz: Path, nome: str, itens: list[dict]) -> None:
    (raiz / ".re" / "modelo" / f"{nome}.json").write_text(json.dumps({"itens": itens}, ensure_ascii=False))


def ler(raiz: Path, nome: str) -> list[dict]:
    return json.loads((raiz / ".re" / "modelo" / f"{nome}.json").read_text())["itens"]


def test_manutencao_em_tres_sessoes(tmp_path: Path) -> None:
    raiz = tmp_path
    (raiz / "docs").mkdir()
    politica = raiz / "docs" / "politica.md"
    politica.write_text("# Política\n\nReembolso acima de R$ 800 exige aprovação do diretor.\n")

    # Sessão 1: levantamento e baseline.
    recop(raiz, "init", "reembolsos")
    fontes = json.loads((raiz / ".re" / "fontes.json").read_text())
    fontes["sistemas"] = [{"id": "SIS-01", "nome": "Portal", "pastas": ["docs"]}]
    (raiz / ".re" / "fontes.json").write_text(json.dumps(fontes))
    recop(raiz, "fontes", "--update")
    gravar(raiz, "requisitos", [
        {"id": "RN-001", "titulo": "Alçada", "enunciado": "Reembolso acima de R$ 800 exige aprovação do diretor.",
         "status": "confirmado", "fontes": ["doc:SIS-01/politica.md#0"], "versao": 1},
        {"id": "RF-001", "titulo": "Fila do diretor", "enunciado": "O sistema envia ao diretor os reembolsos da alçada.",
         "status": "confirmado", "fontes": ["doc:SIS-01/politica.md#0"], "rel": {"depende_de": ["RN-001"]}},
    ])
    gravar(raiz, "backlog", [
        {"id": "EP-001", "titulo": "Aprovação", "status": "proposto"},
        {"id": "US-001", "titulo": "Fila do diretor", "pai": "EP-001", "status": "pronto", "requisitos": ["RF-001"],
         "criterios_aceite": ["Dado reembolso de R$ 900, vai para o diretor"]},
        {"id": "US-002", "titulo": "Histórico", "pai": "EP-001", "status": "pronto", "criterios_aceite": ["Dado…"]},
    ])
    assert recop(raiz, "check").strip() == "ok"
    assert json.loads(recop(raiz, "baseline", "--nota", "v1"))["baseline"] == "B-001"
    assert recop(raiz, "vigiar", "--hook") == "\n"  # nada mudou: hook sem texto

    # Entre sessões, a política muda fora da skill.
    politica.write_text("# Política\n\nReembolso acima de R$ 1.500 exige aprovação do diretor.\n")

    # Sessão 2: o hook avisa, o agente analisa impacto e aplica o CR.
    aviso = recop(raiz, "vigiar", "--hook")
    assert "docs/politica.md" in aviso and "RN-001, RF-001" in aviso
    impacto = json.loads(recop(raiz, "impacto", "RN-001"))
    assert {"RF-001", "US-001"} <= {a["id"] for a in impacto["afetados"]}
    req = ler(raiz, "requisitos")
    req[0] |= {"enunciado": "Reembolso acima de R$ 1.500 exige aprovação do diretor.", "status": "alterado", "versao": 2,
               "historico": [{"versao": 1, "mudanca": "CR-001", "antes": "…acima de R$ 800…"}]}
    gravar(raiz, "requisitos", req)
    backlog = ler(raiz, "backlog")
    backlog[1] |= {"status": "revisar", "criterios_aceite": ["Dado reembolso de R$ 1.600, vai para o diretor"]}
    gravar(raiz, "backlog", backlog)
    gravar(raiz, "mudancas", [{"id": "CR-001", "titulo": "Alçada passa a R$ 1.500", "gatilho": "fonte",
                               "origem": "doc:SIS-01/politica.md#0", "classe": "conflitante", "complexidade": "simples",
                               "afetados": ["RN-001", "RF-001", "US-001"], "status": "aplicada", "baseline": "B-001"}])
    assert recop(raiz, "check").strip() == "ok"
    verif = json.loads(recop(raiz, "verificar", ok=False))
    assert not any("1.500" in json.dumps(v, ensure_ascii=False) for v in verif.values())  # valor novo tem fonte
    recop(raiz, "fontes", "--update")
    assert recop(raiz, "vigiar", "--hook") == "\n"

    # Sessão 3: o que mudou desde a baseline, e só isso vai para o backlog.
    diff = json.loads(recop(raiz, "diff"))
    assert diff["requisitos"]["alterados"] == ["RN-001"] and diff["backlog"]["alterados"] == ["US-001"]
    delta = recop(raiz, "exportar", "jira", "--delta")
    assert "Fila do diretor" in delta and "Histórico" not in delta
    plano = json.loads(recop(raiz, "publicar", "jira", "--delta"))["plano"]
    assert [p["id"] for p in plano] == ["EP-001", "US-001", "US-002"]  # nada publicado ainda: tudo é criação
    assert json.loads(recop(raiz, "baseline", "--nota", "CR-001"))["baseline"] == "B-002"
    assert json.loads(recop(raiz, "diff", "B-002"))["requisitos"]["alterados"] == []
