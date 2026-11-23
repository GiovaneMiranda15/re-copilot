# Motor RAG (`<skill>/engine`, pacote `rag_re_engine`)

O motor é **opcional** e vem junto com a skill. Sem ele, a skill funciona lendo os
arquivos diretamente (Read/Grep) e entrevistando.

## Localizar (uma vez por sessão)

Cada chamada de shell é independente, então variáveis **não** persistem. Descubra o
comando uma vez e depois escreva-o por extenso em toda chamada:

```bash
if command -v uv >/dev/null && [ -f "<skill>/pyproject.toml" ]; then
  echo "ENGINE=uv run --project \"<skill>\" --extra embeddings rag-re-engine"
elif command -v rag-re-engine >/dev/null; then
  echo "ENGINE=rag-re-engine"
else
  echo "ENGINE="
fi
```

- `uv run --project "<skill>" --extra embeddings rag-re-engine`: a versão que vem com a
  skill, **sempre preferida** (o primeiro uso cria o ambiente). O extra é necessário para os
  embeddings semânticos.
- `rag-re-engine` no PATH: só sem `uv`. Pode ser uma instalação antiga: se `--help` não listar
  o comando `build`, trate como indisponível.
- Vazio → avise uma vez (instalação no `README.md` da skill), siga sem RAG e mantenha
  `state.json.indice = null`.

Abaixo, `$ENGINE` representa o comando encontrado.

## Quando usar: modo direto ou RAG

`recop.py fontes` informa `tamanho_kb`. Na validação, com bases pequenas, o RAG dobrou o tempo sem
aumentar a cobertura. Portanto:

| Fontes | Modo | O que fazer |
|---|---|---|
| até 300 KB | **direto** (padrão) | leia os arquivos inteiros. Não indexe nem rode `build`. De dumps, leia só a estrutura e use o motor ou `grep` para filtrar dados |
| acima de 300 KB, ou o usuário pede RAG | **RAG** | indexe, rode `build` e use a estratégia de cada atividade |

Antes de dispensar o motor, teste de verdade: `$ENGINE --help` e uma consulta com LLM. O embedder multilíngue baixa da internet só na primeira vez; sem acesso, use
`--embedder hash` e avise que a busca é lexical. Em subagente, o motor funciona igual. Só registre indisponibilidade
depois de uma falha real, com o erro em `log-rag.jsonl`.

Grave a escolha em `state.json.modo_rag` (`direto | rag`) e informe o usuário. No modo direto, cite
pelo arquivo e pela seção ou objeto. Para experimentos que comparam as arquiteturas, use sempre `rag`.

## Indexar

Ver `fontes.md` §3. Sempre `--db .re/index.db`, um `--sistema` por pasta e o mesmo
embedder (`fastembed:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, ~220 MB
no primeiro uso). Formatos: txt, md, pdf (via `pdftotext`), sql (só estrutura), csv (só cabeçalho e número de linhas).
docx, pptx e xlsx: rode `recop.py extrair` e indexe `.re/extraidos` (o `index` avisa quando encontra esses arquivos).

A busca é **híbrida**: vetorial (sentido) + léxica BM25 (números, códigos, nomes de tabela), fundidas por RRF. Numa base
de centenas de documentos parecidos, a parte léxica é o que acha "filial 137" ou "ck_limite_diaria".

## Consultar

```bash
$ENGINE retrieve --db .re/index.db --activity <atividade> --query "<consulta>" --json -k 5 [--sistema SIS-01,SIS-02] [--llm none]
```

Estratégia por atividade (o motor escolhe e informa em `recommended`/`strategy`/`notes`):

| `--activity` | Use em | Arquitetura indicada | Hoje executa |
|---|---|---|---|
| `elicitacao` | diagnóstico, entrevistas | Agentic RAG | Agentic RAG |
| `analise` | diagnóstico (divergências), análise | Corrective RAG / Self-RAG (empate) | Corrective RAG; force Self-RAG com `--strategy self_rag` |
| `especificacao` | entregáveis, visão de bases longas | RAPTOR (exige `build`) | RAPTOR |
| `validacao` | validação, impacto moderado | Corrective RAG | Corrective RAG |
| `gerenciamento_mudancas` | classificador, CR | Adaptive RAG | Adaptive RAG |
| `rastreabilidade` | matriz, relações entre documentos | GraphRAG (exige `build`) | GraphRAG |

Há dois grafos diferentes: o GraphRAG do motor liga entidades **dos documentos**; o
`recop.py impacto` percorre o grafo **dos requisitos** do projeto. Para impacto de mudança,
comece pelo `recop.py impacto`.

Depois de indexar, construa as estruturas derivadas uma vez (usa LLM; o grafo é incremental
e a árvore é refeita). Se as fontes mudarem, rode de novo: o `trace` avisa quando estão
desatualizadas.

```bash
$ENGINE build --db .re/index.db --what raptor,graph
```

O `build` faz uma chamada de LLM por lote de trechos e pode levar vários minutos: rode em segundo
plano, sem timeout curto. Se for interrompido, rode de novo: o grafo retoma do que falta. Se o
`trace` de uma consulta disser que a estrutura não existe, a resposta veio só por similaridade.

- Agentic, Corrective, Self e Adaptive chamam um LLM na consulta, escolhido por `--llm` (padrão `auto`):

  | `--llm` | Provedor |
  |---|---|
  | `auto` | o primeiro disponível: `claude`, `anthropic`, `openai` |
  | `claude[:modelo]` | Claude Code em modo headless (`claude -p`), sem chave de API |
  | `anthropic[:modelo]` | API da Anthropic (extra `anthropic`; padrão `claude-opus-5-5`) |
  | `openai[:modelo]` | qualquer API compatível com OpenAI (`OPENAI_API_KEY`, `OPENAI_BASE_URL`) |
  | `ollama[:modelo]` | Ollama local (`OLLAMA_HOST`), sem custo de API |

  As tarefas são simples (avaliar trechos, decompor consultas): um modelo menor costuma bastar, e o usuário escolhe. No modo RAG, **use a estratégia da
  atividade por padrão:** é ela que dá o diferencial da skill. Reserve `--llm none` (cai no
  baseline, o motor avisa em `notes`) para sondagens soltas, nunca para sustentar um achado,
  uma divergência, a validação ou a análise de um CR. Se `claude` não estiver disponível,
  registre isso em `log-rag.jsonl` (`evento: falha_motor`) e diga ao usuário. RAPTOR e
  GraphRAG só usam LLM no `build`.
- Se o LLM falhar, a estratégia degrada e registra no `trace`. Não esconda isso do usuário
  quando for relevante. Resumo do RAPTOR (`origin: summary`) não é fonte: cite os trechos
  de `derived_from`.
- Escreva a consulta como afirmação ou termos do domínio, uma por subtema. Para comparar
  sistemas, repita a mesma consulta com `--sistema` diferente.

## Citar

Cada evidência traz `chunk_id` (`SIS-01/schema.sql#2`) e `sistema`. Cite `[doc: <chunk_id>]`
(ou `[sql: <arquivo>:<objeto>]` para triggers, procedures e constraints). Use a evidência
só se o texto realmente sustenta a afirmação: similaridade alta não é prova. CRAG com
`evidence` vazio ou trace `incorrect` = "não encontrado nas fontes".

## Registrar

Após cada `retrieve`, anexe em `.re/log-rag.jsonl`:

```json
{"ts": "<ISO 8601>", "evento": "retrieve", "fase": "<fase>", "perfil": "<perfil|null>", "activity": "…", "sistema": "<filtro|null>", "query": "…", "recommended": "…", "strategy": "…", "n_evidence": 3, "usadas": ["SIS-01/schema.sql#2"], "llm_calls": 2, "latency_s": 4.1}
```

`usadas` = chunks efetivamente citados. Eventos de classificação e impacto: ver `manutencao.md` §6.

## Código do projeto

Não indexe código. Use Grep/Read direcionados (rotas, entidades, migrations, regras,
clientes de integração) e cite `[código: path:linha]`.
