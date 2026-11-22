# re-copilot

Copiloto de **Engenharia de Requisitos** para agentes de IA. Lê os documentos, dumps de banco e telas dos
sistemas que existem, diagnostica o cenário, entrevista você na pele de cada área da empresa, escreve a
documentação de negócio, a documentação técnica e o backlog, e **mantém os requisitos** quando chega informação nova.

*Requirements-engineering copilot for AI agents: source-grounded diagnosis, multi-role interviews, business and
technical docs, Jira/Azure DevOps backlog, and change management with per-stage RAG. Docs in Portuguese.*

> **Estado: experimental (0.4).** Funciona de ponta a ponta e foi validado em casos sintéticos e em um projeto
> real, mas ainda não foi testado com outras pessoas. Veja [o que já está provado](#validação) antes de confiar.

## O que faz

| Etapa | O que você recebe |
|---|---|
| **Fontes** | Lê docs, PDF, dumps SQL (só a estrutura, nunca os dados), CSV, ERDs e telas; classifica cada fonte como vigente, proposta ou legado |
| **Diagnóstico** | Divergências entre sistemas, gargalos, riscos, pontos de apoio e oportunidades, com fonte citada e checagem de falso positivo |
| **Entrevistas** | 19 perfis (negócio, PMO, comercial, financeiro, RH, compras, jurídico, operações, UX, dev, DBA, arquiteto, segurança, QA, DevOps…) e perfis sob demanda |
| **Entregáveis** | BRD, processos, SRS, modelo de dados, integrações, rastreabilidade e backlog, com CSV para Jira e Azure DevOps |
| **Manutenção** | Classifica cada informação nova (nova, existente, conflitante, complementar), mede o impacto no grafo de requisitos, abre pedidos de mudança e versiona por baseline |
| **RAG por etapa** | Agentic, Corrective, Self-RAG, Adaptive, RAPTOR e GraphRAG, cada um na atividade em que costuma ajudar |

O que a diferencia de pedir "levante os requisitos" a uma IA: **checagens que o modelo não consegue burlar**.
`recop.py verificar` recusa número sem fonte em requisito confirmado, requisito "confirmado" apoiado só em proposta
ou código legado, citação inválida, divergência sem checagem de falso positivo e dados sensíveis nos documentos.

## Instalação

Requisitos: `python3` (≥ 3.12). Para o motor RAG e o servidor MCP, [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/GiovaneMiranda15/re-copilot.git
cd re-copilot
```

| Agente | Comando | Estado |
|---|---|---|
| **Claude Code** | `./install.sh` (liga a pasta em `~/.claude/skills/re-copilot`) | testado |
| **Qualquer cliente MCP** | `./install.sh --motor` e `./install.sh --mcp` (mostra a configuração) | testado com cliente stdio |
| Codex CLI | `./install.sh --codex` (bloco em `~/.codex/AGENTS.md`) | experimental |
| Gemini CLI | `./install.sh --gemini` (bloco em `~/.gemini/GEMINI.md`) | experimental |
| Cursor | `./install.sh --cursor <projeto>` (regra em `.cursor/rules/`) | experimental |
| Outro agente | `./install.sh --agents <arquivo de instruções>` | experimental |

A pasta do repositório é a própria skill: `SKILL.md` é o ponto de entrada. Qualquer agente que leia arquivos e rode
comandos consegue seguir o método. "Experimental" significa que o instalador funciona, mas o método ainda não foi
avaliado naquele agente.

### Servidor MCP

```bash
claude mcp add re-copilot -- uv run --project "$PWD" --extra mcp --extra embeddings re-copilot-mcp
```

Oferece o prompt `re-copilot` (o método), as referências e os perfis como recursos, 16 ferramentas `re_*` (modelo,
checagens, rastreabilidade, baseline, exportação, leitura que oculta segredos) e 3 `rag_*` (indexar, buscar,
construir). Configuração para Codex e Cursor: `./install.sh --mcp`.

## Uso

No diretório do projeto que você quer analisar, peça ao agente: **"re-copilot: o escopo é …"**. A skill cria `.re/`
no projeto, registra as fontes, diagnostica, faz as perguntas que faltam e gera os documentos em `.re/entregaveis/`.

Comandos úteis a qualquer momento: `status`, `diagnóstico`, `entrevistar financeiro`, `mudança: <texto>`,
`impacto RN-004`, `verificar`, `baseline`, `entregáveis`. Lista completa em [`SKILL.md`](SKILL.md).

Para ver funcionando sem dados seus, use um dos casos em [`exemplos/`](exemplos), cada um com gabarito.

## RAG e provedores de LLM

O motor (`rag-re-engine`) indexa as fontes com embeddings multilíngues locais e usa LLM em algumas estratégias.
Escolha o provedor com `--llm` (padrão `auto`):

| `--llm` | Provedor |
|---|---|
| `claude` | Claude Code (`claude -p`), sem chave de API |
| `anthropic[:modelo]` | API da Anthropic (`uv sync --extra anthropic`) |
| `openai[:modelo]` | qualquer API compatível com OpenAI (`OPENAI_API_KEY`, `OPENAI_BASE_URL`) |
| `ollama[:modelo]` | Ollama local, sem custo de API |
| `none` | sem LLM: as estratégias que dependem dele usam a busca simples, e o motor avisa |

Por padrão a skill **lê as fontes diretamente até 300 KB** e só usa o RAG acima disso, porque nas bases pequenas
testadas ele custou mais tempo sem melhorar a cobertura. Peça "use RAG" para forçar. Todas as arquiteturas são
adaptações das originais, e cada módulo em `engine/src/rag_re_engine/pipelines/` diz o que foi adaptado.

## Segurança e dados

- Tudo o que a skill lê vai para o modelo que você usa. Use só material que você pode compartilhar assim.
- Fontes são **somente leitura**; a skill escreve só em `.re/`. De dumps e planilhas ela lê estrutura e regras, não
  registros. `recop.py ver` recusa arquivos de credenciais e oculta tokens, senhas e CPF ao ler código.
- `.re/` pode conter trechos dos seus documentos: revise antes de versionar em repositório público.

## Validação

Resultados completos em [`docs/validacao/resultados/`](docs/validacao/resultados); protocolo em
[`docs/validacao/README.md`](docs/validacao/README.md).

| Rodada | Resultado |
|---|---|
| 01: v1 em dois casos sintéticos | Não superou a IA comum nem a skill timovi |
| 02: v3 em caso novo, independente | Melhor documentação (4,86 de 5, contra 4,00), mas **menor cobertura** (92%, contra 99% e 96%) |
| 03: v3 em projeto real | Fiel às notas (36 de 40 cobertas, 0 citações incorretas), com status `confirmado` inflado, corrigido na v4 |

Ainda não provado: se a v4 recuperou a cobertura, se o RAG compensa em bases grandes, a manutenção ao longo de
várias sessões e o uso por outras pessoas. Juízes e oráculos das rodadas são IA, e cada condição rodou uma vez.

## Estrutura

```
SKILL.md          ponto de entrada do método
references/       workflow, modelo, fontes, diagnóstico, entrevista, manutenção, entregáveis, backlog, RAG
roles/            19 perfis e um modelo para perfis novos
scripts/recop.py  utilitário sem dependências: init, check, lint, verificar, render, impacto, pares, ligações,
                  baseline, diff, exportar, ver
engine/           motor RAG e servidor MCP (pacote rag_re_engine)
exemplos/         3 casos sintéticos com gabarito
docs/             desenho e validação
```

## Desenvolvimento

```bash
uv sync --all-extras && uv run pytest
```

Contribuições: [`CONTRIBUTING.md`](CONTRIBUTING.md). Instruções para agentes que trabalham neste repositório:
[`AGENTS.md`](AGENTS.md).

## Origem e licença

Nasceu do TCC "Aplicação de Arquiteturas RAG na Engenharia de Requisitos", de Giovane Luna Miranda.
Licença [MIT](LICENSE).
