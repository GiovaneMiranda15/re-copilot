# Changelog

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
