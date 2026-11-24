# Changelog

## 0.5.1 — correções da validação

- **`esquema` (PostgreSQL) apagava linhas `SET …` de dentro de funções** (a cláusula de um `UPDATE`, por exemplo) e mudava a regra
  extraída. Quem extraiu com a 0.5.0 um banco com funções deve extrair de novo.
- `esquema` (MySQL/MariaDB), agora testado em servidores reais: inclui eventos agendados, dispensa o privilégio PROCESS, não expõe o
  contador `AUTO_INCREMENT`, aceita `mariadb-dump`, remove o ruído de sessão e explica que permissões faltam.
- A saída de `esquema` não muda entre execuções sem mudança no banco (o token `\restrict` do pg_dump saía diferente a cada vez e
  fazia o `vigiar` acusar alteração).
- `rag-re-engine contradicoes`: par sem resposta é repetido e, se faltar, relatado em `sem_resposta`; `cobertura` mostra o que ficou fora;
  `completo` diz se tudo foi julgado; `-n 0` julga todos; se nada foi julgado, é erro, e não "nenhuma contradição".
- `engine/benchmarks/contradicoes.py`: 36 pares rotulados, com 13 armadilhas.

## 0.5.0 — integrações, gatilho automático e busca híbrida

- **Gatilho automático de manutenção:** `recop.py vigiar` lista as fontes que mudaram e os itens que as citam;
  `install.sh --hook <projeto>` leva esse aviso ao início de cada sessão do Claude Code; `--intervalo` vigia em
  segundo plano; ferramenta MCP `re_vigiar`.
- **Contradições de sentido:** `recop.py pares --amplo` (todos os pares do mesmo tema, com enunciados) e
  `rag-re-engine contradicoes` (LLM julga em lotes). MCP: `re_pares(amplo=True)`, `rag_contradicoes`.
- **Jira e Azure DevOps pela API:** `recop.py publicar` (plano sem `--aplicar`; idempotente por `.re/publicado.json`).
- **Banco ao vivo:** `recop.py esquema` extrai só a estrutura de PostgreSQL, MySQL e SQLite, em leitura.
- **docx, pptx, xlsx e csv:** `recop.py extrair` (planilhas só com perfil e agregados); o `index` avisa o que extrair.
- **Busca híbrida:** vetorial + BM25 (FTS5 do SQLite) por RRF em todas as arquiteturas. Em 600 documentos, recall@5
  de 0,15 para 0,87. Embedder em cache (consulta de 1,3 s para 0,1 s).
- Correções: `recop` desatualizado na instalação editável; `parse_json` lendo só o primeiro objeto de uma lista;
  tempo limite do Ollama.
- Testes: manutenção em três sessões (processos separados), 24 ferramentas MCP, benchmark de escala.

## 0.4.0 — primeira versão pública

- Repositório próprio: a raiz é a skill; pacote instalável (`rag-re-engine`, `recop`, `re-copilot-mcp`).
- Servidor MCP com o método (prompt e recursos) e 19 ferramentas.
- Motor com vários provedores de LLM: Claude Code, API da Anthropic, APIs compatíveis com OpenAI e Ollama.
- Instalador para Claude Code, Codex CLI, Gemini CLI, Cursor e qualquer arquivo de instruções.
- Regra de autoridade: proposta e legado não confirmam requisito; citação humana precisa tratar do assunto.
- Novas checagens: `pares` (contradições), `ligacoes` (fontes citadas e não lidas), `ver` (leitura que oculta
  segredos), dados sensíveis nos documentos, requisitos agrupados, confirmados com pergunta aberta.
- Perfis `rh-pessoas` e `suprimentos`; `operacoes` sem viés de logística.
- `recop.py init`; fontes em pastas ligadas por symlink; CSV no índice (só cabeçalho); cache do embedder fora de `/tmp`.

Histórico anterior (v1 a v3) e validação: `docs/validacao/resultados/`.
