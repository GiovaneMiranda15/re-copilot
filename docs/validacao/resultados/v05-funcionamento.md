# Testes de funcionamento da 0.5 (22/11/2026)

Testes do que faltava ou estava testado só em parte na 0.4. São testes de **funcionamento** (a função faz o que diz),
não de qualidade de requisitos: isso é a rodada 04 (`docs/validacao/rodadas/r04-RUNBOOK.md`).

## Resumo

| Item | Como foi testado | Resultado |
|---|---|---|
| Manutenção entre sessões | `tests/test_sessoes.py`: 3 sessões em processos separados, só com o que ficou em `.re/` | ok: aviso da fonte alterada, impacto, CR, diff entre baselines, backlog só do que mudou |
| Gatilho automático (hook) | `install.sh --hook` num projeto, fonte alterada, sessão nova do Claude Code (`claude -p`, sem ferramentas) | ok: o modelo recebeu a fonte alterada e o ID que a cita |
| Servidor MCP em cliente real | Claude Code com `--mcp-config`, chamando `re_vigiar` e `re_status` | ok |
| Banco ao vivo | PostgreSQL 16 em Docker com dados, `recop.py esquema` via `pg_dump --schema-only` | ok: tabelas, FK, CHECK, trigger, função e comentário; nenhum dado |
| Provedor OpenAI-compatível | Ollama local (`qwen3:4b-instruct`) em `rag-re-engine contradicoes` | ok: achou a contradição "folha × PIX em 2 dias", que `pares` (léxico) não acha, e o par complementar certo |
| docx, pptx, xlsx, csv | testes com arquivos gerados | ok; planilha sai só com perfil e agregados |
| Jira e Azure DevOps | testes com API simulada (requisições conferidas: método, URL, autenticação, hierarquia, idempotência) | ok na simulação; **não testado contra instância real** |
| Base grande | `engine/benchmarks/base_grande.py`, 600 documentos | ver abaixo |
| Codex CLI | `AGENTS.md` no projeto, `codex exec` | **não rodou**: a conta de teste não aceita os modelos configurados |
| Gemini CLI | `GEMINI.md` no projeto, `gemini -p` | **não rodou**: o plano gratuito do Gemini Code Assist deixou de aceitar o cliente |

## Escala: 600 documentos

Corpus sintético de 6 sistemas, documentos de texto parecido entre si, um fato plantado por documento
("Na filial 137, o limite de aprovação de vendas é de R$ …"). 150 consultas, k = 5, embedder multilíngue local.
Dados: `escala-600.json`.

| Busca | recall@5 | MRR | latência média | p95 |
|---|---|---|---|---|
| só vetorial (0.4) | 0,153 | 0,107 | 0,09 s | 0,13 s |
| híbrida (0.5) | **0,867** | **0,479** | 0,10 s | 0,14 s |
| Corrective RAG sobre a híbrida, sem LLM | 0,867 | 0,479 | 0,10 s | 0,13 s |

Indexação: 1.621 trechos em 70 s (23 por segundo, CPU), índice de 8,7 MB.

Leitura: o embedding sozinho não separa "filial 137" de "filial 138"; em bases grandes de documentos parecidos isso
derruba a recuperação. A parte léxica resolve identificadores. O caso é adverso de propósito (o fato depende de um
número); em perguntas por sentido a diferença deve ser menor. Os pipelines com LLM não entraram (custo de uma
chamada por consulta); use `rag-re-engine evaluate` numa amostra.

## Bugs encontrados durante os testes

- A instalação editável (`uv run --project`) copiava o `recop.py` para o ambiente, e ele ficava velho após atualizar
  o repositório. Agora o motor e o comando `recop` carregam o `scripts/recop.py` da pasta.
- `parse_json` devolvia só o primeiro objeto quando a resposta era uma lista de objetos.
- O primeiro lote no Ollama estourava o tempo limite com o modelo frio em CPU (agora 600 s, `RE_LLM_TIMEOUT`).
- A busca recarregava o modelo de embeddings a cada consulta (1,3 s); agora fica em cache.
