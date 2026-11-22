"""Testes do utilitário scripts/recop.py (só biblioteca padrão)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recop.py"
spec = importlib.util.spec_from_file_location("recop", SCRIPT)
recop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recop)


def _write(re_dir: Path, name: str, items: list[dict]) -> None:
    (re_dir / "modelo" / f"{name}.json").write_text(json.dumps({"itens": items}))


@pytest.fixture
def re_dir(tmp_path: Path) -> Path:
    re_dir = tmp_path / ".re"
    (re_dir / "modelo").mkdir(parents=True)
    (tmp_path / "fontes" / "erp").mkdir(parents=True)
    (tmp_path / "fontes" / "erp" / "schema.sql").write_text("CREATE TABLE t (id INT);")
    (re_dir / "fontes.json").write_text(json.dumps(
        {"sistemas": [{"id": "SIS-01", "nome": "ERP", "pastas": ["fontes/erp"]}], "fontes": []}))
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "titulo": "Comissão", "enunciado": "O sistema deve…", "status": "confirmado",
         "fontes": ["doc:SIS-01/schema.sql#0"], "sistemas": ["SIS-01"]},
        {"id": "RF-001", "titulo": "Motor", "enunciado": "O sistema deve…", "status": "hipótese",
         "rel": {"depende_de": ["RN-001"]}},
    ])
    _write(re_dir, "achados", [{"id": "DIV-001", "titulo": "x", "status": "aberto", "rel": {"afeta": ["RN-001"]}}])
    _write(re_dir, "backlog", [
        {"id": "EP-001", "tipo": "epico", "titulo": "Comissões", "status": "proposto"},
        {"id": "US-001", "tipo": "historia", "titulo": "Configurar", "pai": "EP-001", "requisitos": ["RF-001"],
         "status": "proposto", "criterios_aceite": ["Dado…"]},
    ])
    return re_dir


def test_check_ok(re_dir: Path) -> None:
    assert recop.check(recop.load(re_dir)) == []


def test_check_detects_problems(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "enunciado": "x", "status": "confirmado"},                      # sem fonte
        {"id": "RN-001", "enunciado": "x", "status": "talvez"},                          # duplicado + status
        {"id": "XX-001", "enunciado": "x", "status": "hipótese", "rel": {"depende_de": ["RF-999"]}},
    ])
    errors = "\n".join(recop.check(recop.load(re_dir)))
    for expected in ("sem fonte", "ID duplicado", "status 'talvez'", "prefixo inválido", "RF-999 não existe"):
        assert expected in errors


def test_render_writes_views(re_dir: Path) -> None:
    paths = recop.render(re_dir, recop.load(re_dir))
    assert {p.name for p in paths} >= {"requisitos.md", "backlog.md", "rastreabilidade.md"}
    matrix = (re_dir / "rastreabilidade.md").read_text()
    assert "| RF-001 | hipótese |" in matrix and "US-001" in matrix
    assert "Sem fonte (órfãos):** RF-001" in matrix
    for title in ("Requisito → fontes", "História → requisito", "Fonte → requisitos", "Divergência → tratamento",
                  "Risco → requisitos", "Pergunta → resposta", "Pendência → histórias", "Mudança → impacto"):
        assert title in matrix
    assert "US-001" in (re_dir / "cenarios.md").read_text()


def test_impacto_traverses_graph_without_expanding_hubs(re_dir: Path) -> None:
    result = recop.impacto(recop.load(re_dir), "RN-001", depth=3)
    found = {a["id"]: a["distancia"] for a in result["afetados"]}
    assert found["RF-001"] == 1 and found["DIV-001"] == 1 and found["US-001"] == 2 and found["EP-001"] == 3
    # SIS-01 aparece, mas não é expandido para outros itens do mesmo sistema
    assert found["SIS-01"] == 1


def test_fontes_detects_new_and_changed(re_dir: Path) -> None:
    first = recop.scan_fontes(re_dir, update=True)
    assert first["novas"] == ["fontes/erp/schema.sql"]
    again = recop.scan_fontes(re_dir, update=False)
    assert (again["novas"], again["alteradas"], again["removidas"]) == ([], [], []) and "tamanho_kb" in again
    (re_dir.parent / "fontes" / "erp" / "schema.sql").write_text("CREATE TABLE t (id INT, x INT);")
    assert recop.scan_fontes(re_dir, update=False)["alteradas"] == ["fontes/erp/schema.sql"]
    registered = json.loads((re_dir / "fontes.json").read_text())["fontes"][0]
    assert registered["id"] == "F-001" and registered["tipo"] == "ddl" and registered["sistema"] == "SIS-01"


def test_impacto_multi_keeps_shortest_distance(re_dir: Path) -> None:
    result = recop.impacto_multi(recop.load(re_dir), ["RN-001", "US-001"], depth=2)
    found = {a["id"]: a["distancia"] for a in result["afetados"]}
    assert "RN-001" not in found and "US-001" not in found
    assert found["RF-001"] == 1


def test_candidatos_ranks_by_overlap_ignoring_accents(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "titulo": "Comissão de vendedor", "enunciado": "Calcular comissão sobre líquido", "status": "confirmado", "fontes": ["x"]},
        {"id": "RF-001", "titulo": "Painel", "enunciado": "Mostrar vendas", "status": "hipótese"},
        {"id": "RF-002", "titulo": "Comissão antiga", "enunciado": "x", "status": "descartado"},
    ])
    result = recop.candidatos(recop.load(re_dir), "a comissao do vendedor sobe para 6%")
    assert result[0]["id"] == "RN-001" and "comissao" in result[0]["termos"]
    assert "RF-002" not in {c["id"] for c in result}  # descartado não é candidato


def test_candidatos_matches_word_roots_with_lower_score(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RF-001", "titulo": "Site", "enunciado": "Manter pagamento por link", "status": "hipótese"},
        {"id": "RN-001", "titulo": "Regra", "enunciado": "Autorizar titular a pagar", "status": "confirmado", "fontes": ["x"]},
    ])
    result = {c["id"]: c["pontos"] for c in recop.candidatos(recop.load(re_dir), "titular pagar")}
    assert "RF-001" in result and result["RN-001"] > result["RF-001"]


def test_baseline_snapshot_and_diff(re_dir: Path) -> None:
    (re_dir / "state.json").write_text(json.dumps({"projeto": "x", "campo_livre": 1}))
    report = recop.criar_baseline(re_dir, recop.load(re_dir), "v1")
    assert report["baseline"] == "B-001"
    state = json.loads((re_dir / "state.json").read_text())
    assert state["baseline"] == "B-001" and state["campo_livre"] == 1
    assert recop.diff_baseline(re_dir, recop.load(re_dir), None)["requisitos"]["alterados"] == []
    model = recop.load(re_dir)
    model["requisitos"][0]["enunciado"] = "novo texto"
    model["requisitos"].append({"id": "RF-009", "enunciado": "x", "status": "hipótese"})
    diff = recop.diff_baseline(re_dir, model, "B-001")["requisitos"]
    assert diff == {"criados": ["RF-009"], "removidos": [], "alterados": ["RN-001"]}
    assert recop.criar_baseline(re_dir, recop.load(re_dir), "v2")["baseline"] == "B-002"


def test_baseline_refuses_open_conflict_and_invalid_model(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [{"id": "RN-001", "enunciado": "x", "status": "conflito"}])
    _write(re_dir, "backlog", [])
    _write(re_dir, "achados", [])
    with pytest.raises(SystemExit, match="conflito"):
        recop.criar_baseline(re_dir, recop.load(re_dir), "x")
    _write(re_dir, "requisitos", [{"id": "RN-001", "enunciado": "x", "status": "talvez"}])
    with pytest.raises(SystemExit, match="integridade"):
        recop.criar_baseline(re_dir, recop.load(re_dir), "x")


BACKLOG = [
    {"id": "EP-001", "tipo": "epico", "titulo": "Pedido, multicanal", "status": "proposto", "prioridade": "Must"},
    {"id": "FT-001", "tipo": "feature", "titulo": "Desconto", "pai": "EP-001", "status": "proposto"},
    {"id": "US-001", "tipo": "historia", "titulo": 'Aprovar "desconto"', "pai": "FT-001", "requisitos": ["RN-001"],
     "descricao": "Como gerente...", "criterios_aceite": ["Dado A\nquando B\nentão C"], "prioridade": "Must",
     "labels": ["área comercial"], "status": "revisar"},
    {"id": "US-002", "tipo": "historia", "titulo": "Sem feature", "pai": "EP-001", "requisitos": [], "status": "proposto"},
    {"id": "US-003", "tipo": "historia", "titulo": "Fora", "pai": "FT-001", "status": "descartado"},
]


def _csv(text: str) -> list[list[str]]:
    import csv
    import io
    return list(csv.reader(io.StringIO(text)))


def test_export_jira_flattens_features_and_links_parents(re_dir: Path) -> None:
    _write(re_dir, "backlog", BACKLOG)
    rows = _csv(recop.export_jira(recop.load(re_dir)))
    assert rows[0][:6] == ["Issue Id", "Parent Id", "Issue Type", "Summary", "Description", "Priority"]
    assert len({len(r) for r in rows}) == 1
    assert [r[2] for r in rows[1:]] == ["Epic", "Story", "Story"]
    story = rows[2]
    assert story[1] == rows[1][0] and story[3] == 'Aprovar "desconto"' and story[5] == "Highest"
    assert "Requisitos: RN-001" in story[4] and "Critérios de aceite" in story[4]
    assert {"req-RN-001", "US-001", "feature-FT-001", "área-comercial"} <= set(story[6:])


def test_export_azure_hierarchy_and_processes(re_dir: Path) -> None:
    _write(re_dir, "backlog", BACKLOG)
    model = recop.load(re_dir)
    rows = _csv(recop.export_azure(model, "agile"))
    assert rows[0][:4] == ["Work Item Type", "Title 1", "Title 2", "Title 3"]
    assert [r[0] for r in rows[1:]] == ["Epic", "Feature", "User Story", "User Story"]
    for r in rows[1:]:
        assert sum(bool(t) for t in r[1:4]) == 1
    assert rows[3][3] == 'Aprovar "desconto"' and rows[3][5].startswith("Dado A") and rows[3][6] == "1"
    assert "req-RN-001" in rows[3][7]
    assert [r[0] for r in _csv(recop.export_azure(model, "scrum"))[1:]][2] == "Product Backlog Item"
    basic = _csv(recop.export_azure(model, "basic"))
    assert basic[0][:3] == ["Work Item Type", "Title 1", "Title 2"] and "Title 3" not in basic[0]
    assert [r[0] for r in basic[1:]] == ["Epic", "Issue", "Issue"]
    assert "feature-FT-001" in basic[2][6]
    with pytest.raises(SystemExit):
        recop.export_azure(model, "cmmi")


def test_export_delta_keeps_only_revisar_and_parents(re_dir: Path) -> None:
    _write(re_dir, "backlog", BACKLOG)
    model = recop.load(re_dir)
    assert [r[3] for r in _csv(recop.export_jira(model, delta=True))[1:]] == ["Pedido, multicanal", 'Aprovar "desconto"']
    assert [r[0] for r in _csv(recop.export_azure(model, "agile", delta=True))[1:]] == ["Epic", "Feature", "User Story"]


def test_export_rejects_orphans(re_dir: Path) -> None:
    _write(re_dir, "backlog", [{"id": "US-001", "titulo": "x", "pai": "FT-999", "status": "proposto"}])
    with pytest.raises(SystemExit, match="US-001"):
        recop.export_jira(recop.load(re_dir))


def test_lint_reports_completeness_gaps(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RF-001", "titulo": "Cadastro", "enunciado": "O sistema deve cadastrar.", "status": "confirmado", "fontes": ["x"], "criterios_aceite": ["a", "b"]},
        {"id": "RF-002", "titulo": "Sem história", "enunciado": "x", "status": "hipótese"},
        {"id": "RNF-001", "titulo": "Rápido", "enunciado": "O sistema deve ser rápido.", "status": "hipótese"},
        {"id": "RNF-002", "titulo": "Latência", "enunciado": "Responder em até 2 s.", "status": "hipótese"},
    ])
    _write(re_dir, "backlog", [
        {"id": "EP-001", "titulo": "E", "status": "proposto"},
        {"id": "US-001", "titulo": "Fraca", "pai": "EP-001", "requisitos": ["RF-001"], "criterios_aceite": ["só um"], "status": "proposto"},
        {"id": "US-002", "titulo": "Sem req", "pai": "EP-001", "criterios_aceite": ["a", "b"], "status": "proposto"},
    ])
    _write(re_dir, "achados", [
        {"id": "RIS-001", "titulo": "sem nada", "status": "aberto"},
        {"id": "RIS-002", "titulo": "com pergunta", "status": "aberto", "gera": ["Q-001"]},
        {"id": "APO-001", "titulo": "apoio", "status": "aberto"},
    ])
    _write(re_dir, "perguntas", [
        {"id": "Q-001", "pergunta": "?", "status": "aberta", "relacionados": ["RF-001"]},
        {"id": "Q-002", "pergunta": "?", "status": "aberta", "relacionados": ["RF-002"]},
    ])
    _write(re_dir, "mudancas", [{"id": "CR-001", "status": "aplicada", "afetados": ["RF-001"]}])
    report = recop.lint(recop.load(re_dir))
    assert report["historias_com_menos_de_2_criterios"] == ["US-001"]
    assert report["historias_sem_requisito"] == ["US-002"]
    assert "RF-002" in report["requisitos_sem_historia"] and "RF-001" not in report["requisitos_sem_historia"]
    assert report["rnf_sem_metrica"] == ["RNF-001"]
    assert report["achados_abertos_sem_tratamento"] == ["RIS-001"]
    assert report["perguntas_abertas_ligadas_a_mudanca"] == ["Q-001"]
    assert "migração" in report["temas_transversais_ausentes"]


def test_lint_theme_detection_ignores_accents(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [{"id": "RF-001", "titulo": "Migração de dados", "enunciado": "x", "status": "hipótese"}])
    assert "migração" not in recop.lint(recop.load(re_dir))["temas_transversais_ausentes"]


def test_lint_flags_confirmed_backed_only_by_hypothesis(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RNF-001", "enunciado": "99,5%", "status": "confirmado", "fontes": ["hipótese:devops"]},
        {"id": "RNF-002", "enunciado": "2 s", "status": "confirmado", "fontes": ["entrevista:qa Q-001"]},
    ])
    assert recop.lint(recop.load(re_dir))["confirmados_apoiados_so_em_hipotese"] == ["RNF-001"]


def _verify_setup(re_dir: Path) -> None:
    (re_dir.parent / "fontes" / "erp" / "schema.sql").write_text(
        "CREATE TRIGGER trg_desc; -- desconto máximo 12% e limite R$ 1.820,00 em 30 dias\n")
    recop.scan_fontes(re_dir, update=True)


def test_verificar_flags_invented_numbers_only_in_confirmed(re_dir: Path) -> None:
    _verify_setup(re_dir)
    _write(re_dir, "requisitos", [
        {"id": "RNF-001", "enunciado": "Disponibilidade de 99,5% e resposta em 3 s.", "status": "confirmado", "fontes": ["x"]},
        {"id": "RNF-002", "enunciado": "Disponibilidade de 99,5%.", "status": "hipótese"},
        {"id": "RN-001", "enunciado": "Limite de R$ 1820 e desconto de 12% em 30 dias.", "status": "confirmado", "fontes": ["x"]},
        {"id": "RN-002", "enunciado": "Conforme RF-200, sem número.", "status": "confirmado", "fontes": ["x"]},
    ])
    _write(re_dir, "achados", [])
    _write(re_dir, "backlog", [])
    found = recop.verificar(re_dir, recop.load(re_dir))["numeros_sem_fonte_em_confirmados"]
    assert sorted(f["valor"] for f in found) == ["3 s", "99,5%"]
    assert {f["id"] for f in found} == {"RNF-001"}


def test_verificar_accepts_number_from_interview_answer(re_dir: Path) -> None:
    _verify_setup(re_dir)
    _write(re_dir, "requisitos", [{"id": "RNF-001", "enunciado": "Em até 45 min.", "status": "confirmado", "fontes": ["x"]}])
    _write(re_dir, "achados", [])
    _write(re_dir, "backlog", [])
    _write(re_dir, "perguntas", [{"id": "Q-001", "pergunta": "?", "status": "respondida", "resposta": "No máximo 45 minutos."}])
    assert recop.verificar(re_dir, recop.load(re_dir))["numeros_sem_fonte_em_confirmados"] == []


def test_verificar_checks_citations(re_dir: Path) -> None:
    _verify_setup(re_dir)
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "enunciado": "x", "status": "confirmado", "fontes": [
            "doc:SIS-01/schema.sql#0", "doc:SIS-01/inventado.md#1", "sql:SIS-01/schema.sql:trg_desc",
            "sql:SIS-01/schema.sql:trg_fantasma", "entrevista:qa Q-099"]},
    ])
    _write(re_dir, "achados", [])
    _write(re_dir, "backlog", [])
    problems = {c["citacao"]: c["problema"] for c in recop.verificar(re_dir, recop.load(re_dir))["citacoes_invalidas"]}
    assert problems == {"doc:SIS-01/inventado.md#1": "arquivo não registrado",
                        "sql:SIS-01/schema.sql:trg_fantasma": "objeto não encontrado",
                        "entrevista:qa Q-099": "pergunta inexistente"}


def test_verificar_requires_false_positive_check_on_divergence(re_dir: Path) -> None:
    _verify_setup(re_dir)
    _write(re_dir, "achados", [
        {"id": "DIV-001", "titulo": "sem", "status": "aberto"},
        {"id": "DIV-002", "titulo": "ok", "status": "aberto", "checagem": {"vigencia": "ambos vigentes", "abrangencia": "mesmo público", "definicao": "mesmo conceito"}},
        {"id": "RIS-001", "titulo": "n/a", "status": "aberto"},
    ])
    assert recop.verificar(re_dir, recop.load(re_dir))["divergencias_sem_checagem_de_falso_positivo"] == ["DIV-001"]


def test_verificar_flags_hypothesis_stories_and_bad_doc_refs(re_dir: Path) -> None:
    _verify_setup(re_dir)
    docs = re_dir.parent / "entrega"
    docs.mkdir()
    (docs / "a.md").write_text("Ver RF-001 e RF-777 em schema.sql e fantasma.csv.")
    report = recop.verificar(re_dir, recop.load(re_dir), docs)
    assert report["historias_de_hipotese_sem_label"] == ["US-001"]
    assert report["ids_inexistentes_nos_documentos"] == {"a.md": ["RF-777"]}
    assert report["arquivos_inexistentes_nos_documentos"] == {"a.md": ["fantasma.csv"]}


def test_lint_flags_decision_masquerading_as_story(re_dir: Path) -> None:
    _write(re_dir, "backlog", [
        {"id": "EP-001", "titulo": "E", "status": "proposto"},
        {"id": "US-001", "titulo": "Definir a alçada de aprovação", "pai": "EP-001", "status": "proposto"},
        {"id": "US-002", "titulo": "Aprovar reembolso", "pai": "EP-001", "status": "proposto"},
    ])
    assert recop.lint(recop.load(re_dir))["historias_que_sao_decisao"] == ["US-001"]


def test_verificar_number_must_match_unit(re_dir: Path) -> None:
    (re_dir.parent / "fontes" / "erp" / "schema.sql").write_text("-- são 3 filiais e 320 admissões por mês\n")
    recop.scan_fontes(re_dir, update=True)
    _write(re_dir, "requisitos", [
        {"id": "RNF-001", "enunciado": "Operar com 320 admissões e responder em até 3 s [hipótese de tempo].", "status": "confirmado", "fontes": ["x"]},
    ])
    _write(re_dir, "achados", [])
    _write(re_dir, "backlog", [])
    found = [f["valor"] for f in recop.verificar(re_dir, recop.load(re_dir))["numeros_sem_fonte_em_confirmados"]]
    assert "3 s" in found and "enunciado com hipótese em item confirmado" in found and "320" not in found


def test_number_normalization() -> None:
    assert recop._number("1.820,00") == "1820" and recop._number("1820") == "1820"
    assert recop._number("99,5") == "99.5" and recop._number("100") == "100" and recop._number("2.000") == "2000"


def _fonte(re_dir: Path, name: str, natureza: str) -> None:
    data = json.loads((re_dir / "fontes.json").read_text())
    data["fontes"].append({"id": f"F-{len(data['fontes']) + 1:03d}", "sistema": "SIS-01", "path": f"fontes/erp/{name}", "natureza": natureza})
    (re_dir / "fontes.json").write_text(json.dumps(data))
    (re_dir.parent / "fontes" / "erp" / name).write_text("texto")


def test_verificar_proposal_or_legacy_alone_cannot_confirm(re_dir: Path) -> None:
    _fonte(re_dir, "proposta.md", "proposta")
    _fonte(re_dir, "legado.md", "legado")
    _fonte(re_dir, "politica.md", "vigente")
    _write(re_dir, "requisitos", [
        {"id": "RF-001", "enunciado": "x", "status": "confirmado", "fontes": ["doc:SIS-01/proposta.md#1"]},
        {"id": "RF-002", "enunciado": "x", "status": "confirmado", "fontes": ["doc:SIS-01/legado.md#1", "doc:SIS-01/proposta.md#2"]},
        {"id": "RF-003", "enunciado": "x", "status": "confirmado", "fontes": ["doc:SIS-01/proposta.md#1", "entrevista:negocio Q-001"]},
        {"id": "RF-004", "enunciado": "x", "status": "confirmado", "fontes": ["doc:SIS-01/politica.md#1"]},
        {"id": "RF-005", "enunciado": "x", "status": "hipótese", "fontes": ["doc:SIS-01/proposta.md#1"]},
    ])
    _write(re_dir, "achados", [])
    _write(re_dir, "backlog", [])
    flagged = {f["id"] for f in recop.verificar(re_dir, recop.load(re_dir))["confirmados_sem_decisao_ou_norma"]}
    assert flagged == {"RF-001", "RF-002"}


def test_lint_new_checks(re_dir: Path) -> None:
    _fonte(re_dir, "lida.md", "vigente")
    _fonte(re_dir, "ignorada.md", "vigente")
    _write(re_dir, "requisitos", [
        {"id": "RF-001", "enunciado": "x", "status": "confirmado", "fontes": ["doc:SIS-01/lida.md#1"]},
        {"id": "RF-002", "enunciado": "x", "status": "hipótese"},
        {"id": "RF-003", "enunciado": "palavra " * 70, "status": "hipótese"},
        {"id": "RF-004", "enunciado": "Conforme na:RF.1, na:RF.2, na:RF.3 e na:RF.4.", "status": "confirmado", "fontes": ["doc:SIS-01/lida.md#1"], "criterios_aceite": ["a"]},
    ])
    _write(re_dir, "perguntas", [{"id": "Q-001", "pergunta": "?", "status": "aberta", "relacionados": ["RF-001", "RF-002"]}])
    report = recop.lint(recop.load(re_dir))
    assert report["confirmados_com_pergunta_aberta"] == ["RF-001"]
    assert set(report["requisitos_agrupados_demais"]) == {"RF-003", "RF-004"}
    assert "fontes/erp/ignorada.md" in report["fontes_sem_nenhum_item"]
    assert "fontes/erp/lida.md" not in report["fontes_sem_nenhum_item"]


def test_pares_finds_polarity_and_value_conflicts_only(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "titulo": "Pagamento de parcela", "enunciado": "Somente o titular pode realizar pagamento da parcela.", "status": "confirmado"},
        {"id": "RF-001", "titulo": "Pagamento público", "enunciado": "Qualquer pessoa faz pagamento da parcela por link.", "status": "confirmado"},
        {"id": "RF-002", "titulo": "Relatório de vendas", "enunciado": "Gerar relatório mensal.", "status": "hipótese"},
        {"id": "RN-002", "titulo": "Prazo de crédito", "enunciado": "Análise de crédito em 1 dia.", "status": "hipótese"},
        {"id": "RN-003", "titulo": "Prazo de crédito", "enunciado": "Análise de crédito em 2 dias.", "status": "hipótese"},
    ])
    pares = recop.pares_revisar(recop.load(re_dir))
    motivos = {(p["a"], p["b"]): p["motivo"] for p in pares}
    assert motivos[("RN-001", "RF-001")] == "polaridade oposta"
    assert motivos[("RN-002", "RN-003")] == "valores diferentes"
    assert not any("RF-002" in k for k in motivos)


def test_pares_skips_registered_conflict(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "titulo": "Pagamento de parcela", "enunciado": "Somente titular faz pagamento da parcela.", "status": "conflito", "rel": {"conflita_com": ["RF-001"]}},
        {"id": "RF-001", "titulo": "Pagamento de parcela", "enunciado": "Qualquer pessoa faz pagamento da parcela.", "status": "conflito"},
    ])
    assert recop.pares_revisar(recop.load(re_dir)) == []


def test_ligacoes_lists_unregistered_and_ignores_urls_images(re_dir: Path) -> None:
    (re_dir.parent / "fontes" / "erp" / "nota.md").write_text(
        "Ver [[Outra Nota]] e [[nota]] e ![[foto.png]] e [doc](sub/extra.md) e https://x.dev/p?magic_link=abc [[Ignorada]]")
    data = json.loads((re_dir / "fontes.json").read_text())
    data["fontes"].append({"id": "F-001", "sistema": "SIS-01", "path": "fontes/erp/nota.md"})
    data["fora_do_escopo"] = ["Ignorada"]
    (re_dir / "fontes.json").write_text(json.dumps(data))
    found = {x["citado"] for x in recop.ligacoes(re_dir, recop.load(re_dir))}
    assert found == {"Outra Nota", "sub/extra.md"}


@pytest.mark.parametrize("texto, tipo", [
    ("Authorization: 'Bearer eyJfaWN0aWNpbw.eyJmYWtl.abc'", "bearer"),
    ("x = eyJfaWN0aWNpbw.abc.def", "jwt"),
    ("https://a.dev/p?magic_link=mc_exemplo_ficticio", "url_com_token"),
    ("senha: minhasenha123", "credencial"),
    ("cliente 123.456.789-09", "cpf"),
])
def test_mascarar_hides_secrets_and_counts_without_values(texto: str, tipo: str) -> None:
    assert "oculto" in recop.mascarar(texto)
    found = recop.achar_sensiveis(texto)
    assert tipo in found and all(isinstance(v, int) for v in found.values())


def test_mascarar_hides_long_quoted_values_and_keeps_code(tmp_path: Path) -> None:
    assert "abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in recop.mascarar('const k = "abcdefghijklmnopqrstuvwxyz0123456789ABCD";')
    assert recop.mascarar("const total = soma(a, b);") == "const total = soma(a, b);"
    f = tmp_path / "c.js"
    f.write_text("linha1\nsenha: abc12345\nlinha3\n")
    assert recop.ver_arquivo(f, "2-3") == "2: [credencial oculto]\n3: linha3"


@pytest.mark.parametrize("nome", [".env", ".env.local", "credentials.json", "google-services.json", "a/b/server.key"])
def test_ver_refuses_credential_files(tmp_path: Path, nome: str) -> None:
    with pytest.raises(SystemExit, match="recusado"):
        recop.ver_arquivo(tmp_path / nome)


def test_verificar_reports_sensitive_data_in_docs_without_values(re_dir: Path) -> None:
    docs = re_dir.parent / "entrega"
    docs.mkdir()
    (docs / "a.md").write_text("Cliente 123.456.789-09 e Bearer abcdefgh12345678")
    report = recop.verificar(re_dir, recop.load(re_dir), docs)
    assert report["dados_sensiveis"]["a.md"] == {"bearer": 1, "cpf": 1}
    assert "123.456" not in json.dumps(report)


def test_render_backlog_marks_hypothesis_and_block(re_dir: Path) -> None:
    _write(re_dir, "backlog", [
        {"id": "EP-001", "titulo": "E", "status": "proposto"},
        {"id": "US-001", "titulo": "Pagar", "pai": "EP-001", "status": "proposto", "labels": ["hipotese"], "bloqueada_por": ["Q-001"], "requisitos": []},
    ])
    _write(re_dir, "perguntas", [{"id": "Q-001", "pergunta": "?", "status": "aberta"}])
    text = recop.render_backlog(recop.load(re_dir))
    assert "US-001 — Pagar [hipótese]" in text and "Bloqueada por: Q-001" in text


def test_pares_exclusivity_uses_word_roots(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "titulo": "Autorização", "enunciado": "O sistema deve autorizar apenas o titular a pagar.", "status": "confirmado"},
        {"id": "RF-001", "titulo": "Site", "enunciado": "O site deve manter pagamento PIX por link.", "status": "hipótese"},
        {"id": "RF-002", "titulo": "Relatório", "enunciado": "Gerar relatório mensal.", "status": "hipótese"},
    ])
    pares = recop.pares_revisar(recop.load(re_dir))
    assert [(p["a"], p["b"]) for p in pares] == [("RN-001", "RF-001")]


def test_verificar_flags_human_citation_unrelated_to_requirement(re_dir: Path) -> None:
    _write(re_dir, "perguntas", [{"id": "Q-001", "pergunta": "A tecnologia de sincronização fica para depois?", "status": "respondida", "resposta": "Sim."}])
    _write(re_dir, "requisitos", [
        {"id": "RNF-001", "titulo": "Carga", "enunciado": "Limitar leitura no Firebird.", "status": "confirmado", "fontes": ["entrevista:g Q-001"]},
        {"id": "RF-001", "titulo": "Sincronização", "enunciado": "Sincronização em até X.", "status": "confirmado", "fontes": ["entrevista:g Q-001"]},
    ])
    _write(re_dir, "achados", [])
    _write(re_dir, "backlog", [])
    found = recop.verificar(re_dir, recop.load(re_dir))["citacao_humana_sem_relacao_com_o_requisito"]
    assert [f["id"] for f in found] == ["RNF-001"]


def test_refs_externas_counts_ranges() -> None:
    assert recop._refs_externas("conforme na:RF.200 a na:RF.203") == 4
    assert recop._refs_externas("conforme na:RF.01 a na:RF.05, em Cielo") == 5
    assert recop._refs_externas("na:RF.50 e na:RF.51") == 2


def test_lint_counts_sources_declared_by_cited_transcription(re_dir: Path) -> None:
    _fonte(re_dir, "lida.md", "vigente")
    _fonte(re_dir, "esquecida.md", "vigente")
    (re_dir / "extraidos").mkdir()
    (re_dir / "extraidos" / "resumo.md").write_text("Lido de lida.md.")
    data = json.loads((re_dir / "fontes.json").read_text())
    data["fontes"].append({"id": "F-009", "sistema": "SIS-01", "path": ".re/extraidos/resumo.md", "natureza": "vigente"})
    (re_dir / "fontes.json").write_text(json.dumps(data))
    _write(re_dir, "requisitos", [{"id": "RF-001", "enunciado": "x", "status": "hipótese", "fontes": ["doc:geral/resumo.md#1"]}])
    report = recop.lint(recop.load(re_dir), re_dir)["fontes_sem_nenhum_item"]
    assert "fontes/erp/esquecida.md" in report and "fontes/erp/lida.md" not in report


def test_ligacoes_strips_table_escape(re_dir: Path) -> None:
    (re_dir.parent / "fontes" / "erp" / "nota.md").write_text("| [[Projeto X\\|Nome]] |")
    data = json.loads((re_dir / "fontes.json").read_text())
    data["fontes"].append({"id": "F-001", "sistema": "SIS-01", "path": "fontes/erp/nota.md"})
    (re_dir / "fontes.json").write_text(json.dumps(data))
    assert recop.ligacoes(re_dir, recop.load(re_dir))[0]["citado"] == "Projeto X"


def test_init_creates_skeleton_and_preserves_existing(tmp_path: Path) -> None:
    re_dir = tmp_path / ".re"
    assert recop.init_projeto(re_dir, "x")
    assert json.loads((re_dir / "state.json").read_text())["modo_rag"] is None
    assert recop.check(recop.load(re_dir)) == []
    (re_dir / "state.json").write_text('{"projeto": "meu"}')
    assert recop.init_projeto(re_dir, "x") == []
    assert json.loads((re_dir / "state.json").read_text()) == {"projeto": "meu"}


def test_fontes_follow_symlinked_folders(tmp_path: Path) -> None:
    fora = tmp_path / "fora" / "sub"
    fora.mkdir(parents=True)
    (fora / "a.md").write_text("x")
    root = tmp_path / "proj"
    (root / ".re").mkdir(parents=True)
    (root / "fontes" / "s").mkdir(parents=True)
    (root / "fontes" / "s" / "link").symlink_to(tmp_path / "fora")
    (root / ".re" / "fontes.json").write_text(json.dumps({"sistemas": [{"id": "SIS-01", "pastas": ["fontes/s"]}], "fontes": []}))
    assert recop.scan_fontes(root / ".re", update=False)["novas"] == ["fontes/s/link/sub/a.md"]
