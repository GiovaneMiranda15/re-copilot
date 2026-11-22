"""Coerência da skill: perfis completos, referências e comandos documentados existem."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SECOES = ("**Postura:**", "**Ótica:**", "## Consultar antes de perguntar", "## Temas e perguntas-semente",
          "## Requisitos que costuma revelar", "## Sinais de alerta", "## Não é com este perfil")
PERFIS = sorted(p for p in (ROOT / "roles").glob("*.md") if p.name != "_template.md")
DOCS = [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md"))]


@pytest.mark.parametrize("perfil", PERFIS, ids=lambda p: p.stem)
def test_perfil_completo(perfil: Path) -> None:
    text = perfil.read_text()
    assert not [s for s in SECOES if s not in text]
    assert len(re.findall(r"^- \*\*", text, re.M)) >= 5


@pytest.mark.parametrize("perfil", PERFIS, ids=lambda p: p.stem)
def test_perfil_encaminha_para_perfis_existentes(perfil: Path) -> None:
    for grupo in re.findall(r"→ ([a-z-]+(?:/[a-z-]+)*)", perfil.read_text()):
        for nome in grupo.split("/"):
            assert (ROOT / "roles" / f"{nome}.md").exists(), nome


def test_todos_os_perfis_estao_no_workflow() -> None:
    workflow = (ROOT / "references" / "workflow.md").read_text()
    assert not [p.stem for p in PERFIS if p.stem not in workflow]


def test_comandos_documentados_existem() -> None:
    script = (ROOT / "scripts" / "recop.py").read_text()
    comandos = set(re.findall(r'add_parser\("(\w+)"', script))
    citados = set(re.findall(r"recop\.py (\w+)", " ".join(d.read_text() for d in DOCS)))
    assert citados <= comandos, citados - comandos
    assert comandos <= citados | {"init"} or not (comandos - citados - {"init"})


def test_referencias_citadas_existem() -> None:
    skill = (ROOT / "SKILL.md").read_text()
    for nome in re.findall(r"`references/([a-z-]+\.md)`", skill):
        assert (ROOT / "references" / nome).exists(), nome


def test_descricao_cabe_no_limite() -> None:
    desc = re.search(r"^description: (.*)$", (ROOT / "SKILL.md").read_text(), re.M).group(1)
    assert len(desc) <= 1024


def test_skill_nao_contem_termos_dos_casos_de_teste() -> None:
    """Exemplos da skill não podem antecipar as respostas dos casos usados na validação."""
    texto = " ".join(p.read_text() for p in [*DOCS, *PERFIS]).lower()
    for termo in ("vendamax", "caliandra", "suprimax", "manutclin", "fn_valida_desconto"):
        assert termo not in texto, termo
