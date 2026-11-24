"""Testes dos comandos da 0.5: pares amplos, vigiar, extrair, esquema e publicar."""

from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recop.py"
spec = importlib.util.spec_from_file_location("recop_novos", SCRIPT)
recop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recop)


def _write(re_dir: Path, name: str, items: list[dict]) -> None:
    (re_dir / "modelo" / f"{name}.json").write_text(json.dumps({"itens": items}))


@pytest.fixture
def re_dir(tmp_path: Path) -> Path:
    recop.init_projeto(tmp_path / ".re", "teste")
    return tmp_path / ".re"


# ------------------------------------------------------------------ pares amplos

def test_pares_amplos_lista_contradicao_sem_sinal_lexico(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "enunciado": "O reembolso é pago na folha do mês seguinte à aprovação.", "status": "hipótese"},
        {"id": "RF-001", "enunciado": "O reembolso aprovado é pago por PIX em até 2 dias úteis.", "status": "hipótese"},
        {"id": "RF-002", "enunciado": "O painel mostra os indicadores de vendas.", "status": "hipótese"},
        {"id": "RF-003", "enunciado": "O reembolso aprovado entra no relatório mensal.", "status": "hipótese",
         "rel": {"complementa": ["RN-001"]}},
    ])
    model = recop.load(re_dir)
    assert not any({p["a"], p["b"]} == {"RN-001", "RF-001"} for p in recop.pares_revisar(model))
    amplos = recop.pares_amplos(model)
    ids = [{p["a"], p["b"]} for p in amplos]
    assert ids[0] == {"RN-001", "RF-001"}
    assert {"RN-001", "RF-003"} not in ids          # já ligados
    assert all("RF-002" not in par for par in ids)  # tema diferente
    assert amplos[0]["enunciado_a"] and amplos[0]["enunciado_b"]


def test_pares_amplos_marca_negacao_de_um_lado(re_dir: Path) -> None:
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "enunciado": "Cobrador pode cancelar boleto em campo.", "status": "hipótese"},
        {"id": "RN-002", "enunciado": "Cobrador não cancela boleto; só a central.", "status": "hipótese"},
    ])
    assert "negação de um lado só" in recop.pares_amplos(recop.load(re_dir))[0]["sinais"]


# ------------------------------------------------------------------ vigiar

def _projeto_com_fonte(re_dir: Path) -> Path:
    raiz = re_dir.parent
    (raiz / "docs").mkdir()
    (raiz / "docs" / "politica.md").write_text("Limite de 300 por dia.")
    fontes = json.loads((re_dir / "fontes.json").read_text())
    fontes["sistemas"] = [{"id": "SIS-01", "nome": "Portal", "pastas": ["docs"]}]
    (re_dir / "fontes.json").write_text(json.dumps(fontes))
    recop.scan_fontes(re_dir, update=True)
    _write(re_dir, "requisitos", [
        {"id": "RN-001", "enunciado": "Limite de 300 por dia.", "status": "confirmado", "fontes": ["doc:SIS-01/politica.md#0"]},
        {"id": "RN-002", "enunciado": "Outro.", "status": "hipótese", "fontes_id": ["F-001"]},
        {"id": "RN-003", "enunciado": "Sem relação.", "status": "hipótese"},
    ])
    return raiz


def test_vigiar_aponta_fontes_alteradas_e_itens_que_as_citam(re_dir: Path) -> None:
    raiz = _projeto_com_fonte(re_dir)
    assert recop.vigiar(re_dir)["mudancas"] == 0
    assert recop.mensagem_vigiar(recop.vigiar(re_dir)) == ""
    (raiz / "docs" / "politica.md").write_text("Limite de 400 por dia.")
    (raiz / "docs" / "nova.md").write_text("x")
    rel = recop.vigiar(re_dir)
    assert rel["alteradas"] == ["docs/politica.md"] and rel["novas"] == ["docs/nova.md"]
    assert rel["itens_afetados"] == {"docs/politica.md": ["RN-001", "RN-002"]}
    texto = recop.mensagem_vigiar(rel)
    assert "RN-001, RN-002" in texto and "fontes --update" in texto
    assert json.loads((re_dir / "fontes.json").read_text())["fontes"][0]["sha256"] != recop.sha256(raiz / "docs" / "politica.md")


def test_vigiar_hook_silencioso_sem_re(tmp_path: Path, capsys) -> None:
    assert recop.main(["--re", str(tmp_path / ".re"), "vigiar", "--hook"]) == 0
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------------ extrair

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(path: Path) -> None:
    corpo = (f'<w:document {W}><w:body>'
             '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Política</w:t></w:r></w:p>'
             '<w:p><w:r><w:t>Limite de R$ 300 </w:t></w:r><w:r><w:t>por dia.</w:t></w:r></w:p>'
             '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cargo</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Limite</w:t></w:r></w:p></w:tc></w:tr>'
             '<w:tr><w:tc><w:p><w:r><w:t>Diretor</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>500</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
             '</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", corpo)


def _xlsx(path: Path, linhas: list[list[str]]) -> None:
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    textos = sorted({v for lin in linhas for v in lin if not v.replace(".", "").isdigit()})
    idx = {t: i for i, t in enumerate(textos)}
    rows = []
    for r, lin in enumerate(linhas, 1):
        cells = []
        for c, v in enumerate(lin):
            ref = f"{chr(65 + c)}{r}"
            cells.append(f'<c r="{ref}"><v>{v}</v></c>' if v.replace(".", "").isdigit()
                         else f'<c r="{ref}" t="s"><v>{idx[v]}</v></c>')
        rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                                       '<sheets><sheet name="Pedidos" sheetId="1" r:id="rId1"/></sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        zf.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{t}</t></si>" for t in textos) + "</sst>")
        zf.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(rows)}</sheetData></worksheet>')


def test_extrair_docx_titulos_paragrafos_e_tabela(re_dir: Path) -> None:
    arq = re_dir.parent / "politica.docx"
    _docx(arq)
    saida = recop.extrair(arq, re_dir, "SIS-01")
    texto = saida.read_text()
    assert saida.name == "SIS-01-politica.md" and "Transcrição de `politica.docx`" in texto
    assert "## Política" in texto and "Limite de R$ 300 por dia." in texto and "| Diretor | 500 |" in texto


def test_extrair_xlsx_so_agregados_sem_registros(re_dir: Path) -> None:
    nomes = [f"Cliente{i:02d}" for i in range(12)]
    linhas = [["cliente", "status", "valor"]] + [[nomes[i], ["aberto", "pago"][i % 2], str(100 + i)] for i in range(12)]
    arq = re_dir.parent / "pedidos.xlsx"
    _xlsx(arq, linhas)
    texto = recop.extrair(arq, re_dir).read_text()
    assert "12 linha(s) de dados" in texto and "categorias: aberto, pago" in texto and "mín 100, máx 111" in texto
    assert "Cliente03" not in texto  # alta cardinalidade: nenhum valor sai


def test_extrair_csv_e_recusas(re_dir: Path) -> None:
    arq = re_dir.parent / "a.csv"
    arq.write_text("id;cpf\n1;123.456.789-09\n2;987.654.321-00\n")
    texto = recop.extrair(arq, re_dir).read_text()
    assert "2 linha(s)" in texto and "123.456" not in texto
    with pytest.raises(SystemExit, match="não suportado"):
        recop.extrair(re_dir.parent / "x.odt", re_dir)
    with pytest.raises(SystemExit, match="credenciais"):
        recop.extrair(re_dir.parent / ".env", re_dir)


def test_extrair_pptx(re_dir: Path) -> None:
    arq = re_dir.parent / "kickoff.pptx"
    ns = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    with zipfile.ZipFile(arq, "w") as zf:
        for i, t in ((2, "Prazo: março"), (1, "Objetivo")):
            zf.writestr(f"ppt/slides/slide{i}.xml", f'<p:sld xmlns:p="x" {ns}><a:p><a:r><a:t>{t}</a:t></a:r></a:p></p:sld>')
    texto = recop.extrair(arq, re_dir).read_text()
    assert texto.index("Objetivo") < texto.index("Prazo: março")


# ------------------------------------------------------------------ esquema

def test_esquema_sqlite_somente_estrutura(tmp_path: Path) -> None:
    db = tmp_path / "loja.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE pedido (id INTEGER PRIMARY KEY, valor NUMERIC CHECK (valor > 0))")
    con.execute("CREATE INDEX ix_valor ON pedido(valor)")
    con.execute("INSERT INTO pedido VALUES (1, 99.9)")
    con.commit()
    con.close()
    ddl = recop.esquema_banco(f"sqlite:///{db}")
    assert "CREATE TABLE pedido" in ddl and "CHECK (valor > 0)" in ddl and "ix_valor" in ddl
    assert "99.9" not in ddl and "INSERT" not in ddl


def test_esquema_postgres_usa_pg_dump_schema_only_e_recusa_senha() -> None:
    chamadas = []

    def runner(cmd, env):
        chamadas.append(cmd)
        return SimpleNamespace(returncode=0, stdout="SET row_security = off;\nCREATE TABLE a (id int);\n", stderr="")

    ddl = recop.esquema_banco("postgresql://leitor@db:5432/erp", runner=runner)
    assert "--schema-only" in chamadas[0] and "CREATE TABLE a" in ddl and "row_security" not in ddl
    with pytest.raises(SystemExit, match="senha"):
        recop.esquema_banco("postgresql://leitor:segredo@db/erp", runner=runner)
    with pytest.raises(SystemExit, match="não suportado"):
        recop.esquema_banco("oracle://x/y", runner=runner)


def test_esquema_mysql_no_data() -> None:
    chamadas = []
    recop.esquema_banco("mysql://leitor@db:3307/loja",
                        runner=lambda cmd, env: chamadas.append(cmd) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    assert "--no-data" in chamadas[0] and chamadas[0][-1] == "loja" and "3307" in chamadas[0]
    assert "--events" in chamadas[0] and "--no-tablespaces" in chamadas[0]
    with pytest.raises(SystemExit, match="SHOW VIEW"):
        recop.esquema_banco("mysql://leitor@db/loja", runner=lambda cmd, env: SimpleNamespace(
            returncode=2, stdout="", stderr="SHOW VIEW command denied to user 'leitor'"))


def test_limpar_dump_preserva_set_dentro_de_funcao() -> None:
    pg = ("\\restrict AbC123\n-- Dumped by pg_dump version 16.1\nSET statement_timeout = 0;\nSET default_tablespace = '';\n"
          "CREATE FUNCTION fechar() AS $$\nUPDATE pedido\nSET status = 'bloqueado'\nWHERE id = p;\n"
          "SET status = 'x';\n$$;\n\\unrestrict AbC123\n")
    limpo = recop._limpar_dump(pg)
    assert "SET status = 'bloqueado'" in limpo and "SET status = 'x';" in limpo
    assert "statement_timeout" not in limpo and "restrict" not in limpo and "Dumped" not in limpo
    my = ("/*!40101 SET NAMES utf8mb4 */;\nCREATE TABLE `c` (\n  `id` int\n) ENGINE=InnoDB AUTO_INCREMENT=8123 DEFAULT CHARSET=utf8mb4;\n"
          "SET @saved_cs_client     = @@character_set_client;\n/*!50001 CREATE VIEW `v` AS SELECT \n 1 AS `id`,\n 1 AS `n`*/;\n"
          "/*!50003 CREATE*/ /*!50003 TRIGGER `t` BEFORE INSERT ON `c` FOR EACH ROW BEGIN\nSET NEW.status='aberto';\nEND */;;\n"
          "/*!50001 VIEW `v` AS select 1 */;\n")
    limpo = recop._limpar_dump(my)
    assert "SET NEW.status='aberto';" in limpo and "VIEW `v` AS select 1" in limpo and "TRIGGER `t`" in limpo
    assert "8123" not in limpo and "1 AS `id`" not in limpo and "SET NAMES" not in limpo and "@saved_cs_client" not in limpo


# ------------------------------------------------------------------ publicar

def _backlog(re_dir: Path) -> None:
    _write(re_dir, "backlog", [
        {"id": "EP-001", "titulo": "Reembolsos", "status": "proposto"},
        {"id": "FT-001", "titulo": "Aprovação", "pai": "EP-001", "status": "proposto"},
        {"id": "US-001", "titulo": "Aprovar", "pai": "FT-001", "status": "proposto", "prioridade": "Must",
         "criterios_aceite": ["Dado <x>"], "requisitos": ["RF-001"]},
    ])


class FakeAPI:
    def __init__(self) -> None:
        self.reqs = []
        self.n = 0

    def __call__(self, req):
        self.n += 1
        corpo = json.loads(req.data) if req.data else None
        self.reqs.append((req.get_method(), req.full_url, corpo, dict(req.headers)))
        resposta = {"key": f"RE-{self.n}"} if "atlassian" in req.full_url else {"id": 100 + self.n}
        return io.BytesIO(json.dumps(resposta).encode())


def test_publicar_sem_aplicar_so_planeja(re_dir: Path) -> None:
    _backlog(re_dir)
    rel = recop.publicar(re_dir, recop.load(re_dir), "jira")
    assert not rel["aplicado"] and [p["id"] for p in rel["plano"]] == ["EP-001", "US-001"]
    assert rel["plano"][1]["pai"] == "EP-001" and "feature-FT-001" in rel["plano"][1]["labels"]
    assert not (re_dir / "publicado.json").exists()


def test_publicar_jira_cria_e_depois_atualiza(re_dir: Path, monkeypatch) -> None:
    _backlog(re_dir)
    for k, v in {"JIRA_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b", "JIRA_TOKEN": "t", "JIRA_PROJETO": "RE"}.items():
        monkeypatch.setenv(k, v)
    api = FakeAPI()
    recop.publicar(re_dir, recop.load(re_dir), "jira", aplicar=True, opener=api)
    (m1, u1, c1, h1), (m2, u2, c2, _) = api.reqs
    assert m1 == "POST" and c1["fields"]["issuetype"]["name"] == "Epic" and h1["Authorization"].startswith("Basic ")
    assert c2["fields"]["parent"] == {"key": "RE-1"} and "Critérios de aceite" in c2["fields"]["description"]
    assert json.loads((re_dir / "publicado.json").read_text()) == {"jira": {"EP-001": "RE-1", "US-001": "RE-2"}}
    recop.publicar(re_dir, recop.load(re_dir), "jira", aplicar=True, opener=api)
    assert [(m, u.rsplit("/", 1)[1]) for m, u, _, _ in api.reqs[2:]] == [("PUT", "RE-1"), ("PUT", "RE-2")]


def test_publicar_azure_hierarquia_completa(re_dir: Path, monkeypatch) -> None:
    _backlog(re_dir)
    for k, v in {"AZURE_DEVOPS_ORG": "https://dev.azure.com/org", "AZURE_DEVOPS_PROJETO": "Meu Projeto",
                 "AZURE_DEVOPS_PAT": "p"}.items():
        monkeypatch.setenv(k, v)
    api = FakeAPI()
    rel = recop.publicar(re_dir, recop.load(re_dir), "azure", aplicar=True, opener=api)
    assert [p["tipo"] for p in rel["feitos"]] == ["Epic", "Feature", "User Story"]
    _, url3, ops3, h3 = api.reqs[2]
    assert "Meu%20Projeto" in url3 and "$User%20Story" in url3 and h3["Content-type"] == "application/json-patch+json"
    rel_pai = [o for o in ops3 if o["path"] == "/relations/-"][0]["value"]
    assert rel_pai["url"].endswith("/102") and any(o["path"].endswith("Priority") and o["value"] == 1 for o in ops3)
    assert "&lt;x&gt;" in [o for o in ops3 if o["path"].endswith("AcceptanceCriteria")][0]["value"]


def test_publicar_exige_variaveis(re_dir: Path, monkeypatch) -> None:
    _backlog(re_dir)
    monkeypatch.delenv("JIRA_URL", raising=False)
    with pytest.raises(SystemExit, match="JIRA_URL"):
        recop.publicar(re_dir, recop.load(re_dir), "jira", aplicar=True, opener=FakeAPI())
