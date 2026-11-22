# Instruções para agentes que trabalham neste repositório

Este repositório é a skill re-copilot. Para **usar** a skill num projeto, leia `SKILL.md`. As instruções abaixo são
para quem **desenvolve** a skill.

- A raiz do repositório é a pasta da skill (`<skill>` nas referências). Mantenha-a autocontida: nada pode depender
  de arquivos fora dela.
- `scripts/recop.py` usa só a biblioteca padrão do Python. Não adicione dependências a ele.
- O motor fica em `engine/src/rag_re_engine`; o servidor MCP, em `mcp_server.py`. Provedores de LLM, em `llm.py`.
- Mudou um comando do `recop.py`? Documente nas referências: `tests/test_skill.py` falha se um comando citado não existir.
- Exemplos nas referências e nos perfis não podem antecipar as respostas dos casos de `exemplos/`; o mesmo teste verifica isso.
- Nada de dados reais, segredos ou dados pessoais em exemplos, testes ou documentação.
- Rode `uv run pytest` antes de entregar. Mudanças no método devem ser medidas com o protocolo de `docs/validacao/`.
