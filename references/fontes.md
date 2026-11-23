# Fontes — sistemas, extração e detecção de mudança

Acesso **somente leitura**. Nada fora de `.re/` é alterado.

## 1. Registrar sistemas

Pergunte ao usuário quais sistemas e "não sistemas" participam do processo: ERPs,
sistemas web, planilhas, e-mails padronizados, processos em papel. Para cada um, grave em
`fontes.json.sistemas`: `id` (`SIS-NN`), `nome`, `papel`, `descricao`, `pastas` (onde estão
as fontes dele, relativas à raiz do projeto). Documentação transversal (políticas, atas,
contratos) vai no sistema `geral`.

## 2. Registrar e extrair fontes

```bash
python3 -I <skill>/scripts/recop.py fontes --update   # registra os arquivos das pastas com hash
```

**Classifique a natureza de cada fonte** em `fontes[].natureza`. É o que define o peso dela:

| Natureza | O que é | Pode confirmar requisito? |
|---|---|---|
| `vigente` | política, contrato, norma ou decisão aprovada | sim |
| `proposta` | especificação, ADR ou plano ainda não aprovado, inclusive os seus | não: gera `hipótese` |
| `legado` | código, banco, telas e manual do sistema antigo | não: prova o que existe hoje, não o que o novo deve fazer |

Na dúvida, use `proposta` e pergunte. Registre em `elementos.json` o que o legado faz; só vira requisito com decisão.

**Procure o que foi citado e não lido:** rode `recop.py ligacoes`. Para cada item relevante, registre e leia a fonte,
ou liste em `fontes.json.fora_do_escopo` e diga isso no diagnóstico. Nos relatórios, deixe claro o que foi só
pesquisado e não lido por inteiro. Fonte sem nenhum item aparece no `lint` (`fontes_sem_nenhum_item`); marque
`sem_conteudo_relevante: true` depois de ler, se for o caso.

**Importe as perguntas pendentes:** se uma fonte tiver perguntas em aberto, traga as que afetam o escopo para
`perguntas.json`, com `relacionados`. O `recop.py` só enxerga o que está no modelo.

**Código e arquivos que podem conter credenciais:** leia com `recop.py ver <arquivo> [--linhas 10-40]`, que recusa
arquivos de credenciais e oculta tokens, senhas e CPF. Não use `cat` nem `sed` nesses casos.

Por formato:

| Formato | Ação |
|---|---|
| txt, md, pdf | indexa direto |
| `.sql` (dump/backup) | indexa direto: o motor mantém só a estrutura (DDL, constraints, procedures, triggers, comments) e descarta `INSERT`/`COPY`. Sem motor: leia o arquivo **filtrando** com `grep -v -iE '^(INSERT\|COPY)'` ou equivalente; nunca carregue blocos de dados |
| ERD (png, jpg, pdf de imagem) | leia a imagem e transcreva para `.re/extraidos/<sistema>-<nome>.md`: entidades, atributos-chave, relações e cardinalidades (Mermaid `erDiagram`) e observações |
| BPMN, drawio (XML) | extraia raias, tarefas, gateways e fluxos para `.re/extraidos/…md` (processo em lista numerada) |
| csv | `recop.py extrair` gera o mesmo perfil do xlsx; o motor sozinho indexa só o cabeçalho. Analise as linhas com script para achar padrões e contagens (agregados, nunca registros) e transcreva cabeçalhos, tipos, regras e agregados para `.re/extraidos/`. Sem dados pessoais |
| docx, pptx | `recop.py extrair <arquivo> --sistema SIS-01`: transcreve para `.re/extraidos/` (títulos, parágrafos, tabelas, slides) |
| xlsx | `recop.py extrair <arquivo>`: só cabeçalho, contagem e perfil das colunas (tipo, preenchimento, mín/máx, categorias de baixa cardinalidade). Nunca registros |
| código-fonte | não indexe; use Grep/Read direcionados (rotas, entidades, regras) e cite `[código: path:linha]` |

**Banco ao vivo (só leitura, só estrutura):** quando o usuário autorizar e fornecer o acesso, extraia o DDL sem dados:

```bash
python3 -I <skill>/scripts/recop.py esquema "postgresql://usuario_leitura@host:5432/banco" --sistema SIS-01
python3 -I <skill>/scripts/recop.py esquema "mysql://usuario_leitura@host/banco" --sistema SIS-02
python3 -I <skill>/scripts/recop.py esquema "sqlite:///caminho/arquivo.db" --sistema SIS-03
```

Usa `pg_dump --schema-only` e `mysqldump --no-data` (cliente instalado na máquina) ou o SQLite em modo somente
leitura. A senha vai por `PGPASSWORD`/`MYSQL_PWD`, que o usuário define; o comando recusa DSN com senha. Peça um
usuário só de leitura. O resultado vai para `.re/extraidos/<sistema>-esquema.sql` e é indexado como um dump.

Transcrições em `.re/extraidos/` são indexadas com o mesmo `--sistema` da fonte original.
Registre a transcrição como fonte, citando a original na primeira linha.

## 3. Indexar (com motor)

Uma chamada por pasta de sistema, sempre no mesmo `--db` e com o mesmo embedder:

```bash
$ENGINE index <pasta> --db .re/index.db --sistema SIS-01 --embedder fastembed:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
$ENGINE index .re/extraidos --db .re/index.db --sistema SIS-01   # se houver transcrições daquele sistema
```

O `doc_id` fica prefixado pelo sistema (`SIS-01/schema.sql#2`), o que torna a citação
autoexplicativa. Reindexar a mesma pasta substitui os chunks antigos. Atualize
`fontes[].indexado_em` e `state.json.indice`.

## 4. Detectar mudança

```bash
python3 -I <skill>/scripts/recop.py fontes            # só mostra
python3 -I <skill>/scripts/recop.py fontes --update   # registra hashes novos
```

- **novas / alteradas:** extraia e indexe de novo; leia o conteúdo novo (para alteradas,
  compare com o que o modelo já cita daquela fonte) e passe cada informação relevante pelo
  classificador (`manutencao.md`, gatilho `fonte`).
- **removidas:** liste os itens do modelo que citam a fonte e pergunte ao usuário se
  continuam válidos.

Rode `fontes` sempre que a skill for ativada num projeto existente.
