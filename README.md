# re-copilot

Copiloto de **Engenharia de Requisitos** para agentes de IA. Lê os documentos, dumps de banco e telas dos
sistemas que existem, diagnostica o cenário, entrevista você na pele de cada área da empresa, escreve a
documentação de negócio, a documentação técnica e o backlog, e **mantém os requisitos** quando chega informação nova.

*Requirements-engineering copilot for AI agents: source-grounded diagnosis, multi-role interviews, business and
technical docs, Jira/Azure DevOps backlog, and change management with per-stage RAG. Docs in Portuguese.*

> **Estado: beta (0.5).** Funciona de ponta a ponta e foi validado em casos sintéticos, em um projeto real e em
> clientes reais (Claude Code com skill, hook e MCP), mas ainda não foi testado com outras pessoas. Veja
> [o que já está provado](#validação) antes de confiar.

## O que faz

| Etapa | O que você recebe |
|---|---|
| **Fontes** | Lê docs, PDF, docx, pptx, dumps SQL (só a estrutura, nunca os dados), planilhas (só perfil e agregados), ERDs e telas; extrai a estrutura de bancos ao vivo (PostgreSQL, MySQL, SQLite) em modo leitura; classifica cada fonte como vigente, proposta ou legado |
| **Diagnóstico** | Divergências entre sistemas, gargalos, riscos, pontos de apoio e oportunidades, com fonte citada e checagem de falso positivo |
| **Entrevistas** | 19 perfis (negócio, PMO, comercial, financeiro, RH, compras, jurídico, operações, UX, dev, DBA, arquiteto, segurança, QA, DevOps…) e perfis sob demanda |
| **Entregáveis** | BRD, processos, SRS, modelo de dados, integrações, rastreabilidade e backlog, com CSV ou publicação direta no Jira e no Azure DevOps pela API |
| **Manutenção** | Avisa sozinha quando uma fonte muda e quais requisitos a citam; classifica cada informação nova (nova, existente, conflitante, complementar), mede o impacto no grafo, abre pedidos de mudança e versiona por baseline |
| **Contradições** | Checagem léxica e julgamento por LLM dos pares do mesmo tema, para pegar contradições de sentido |
| **RAG por etapa** | Agentic, Corrective, Self-RAG, Adaptive, RAPTOR e GraphRAG, cada um na atividade em que costuma ajudar, sobre busca híbrida (vetorial + BM25) |

O que a diferencia de pedir "levante os requisitos" a uma IA: **checagens que o modelo não consegue burlar**.
`recop.py verificar` recusa número sem fonte em requisito confirmado, requisito "confirmado" apoiado só em proposta
ou código legado, citação inválida, divergência sem checagem de falso positivo e dados sensíveis nos documentos.

## Instalação

Requisitos: `python3` (≥ 3.12). Para o motor RAG e o servidor MCP, [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/GiovaneMiranda15/re-copilot.git
cd re-copilot
./install.sh            # Claude Code
./install.sh --motor    # opcional: motor RAG e servidor MCP
```

Sem clonar, só o motor e o servidor MCP: `uvx --from git+https://github.com/GiovaneMiranda15/re-copilot re-copilot-mcp`
(ou o wheel anexado a cada [release](https://github.com/GiovaneMiranda15/re-copilot/releases)).

| Agente | Comando | Estado |
|---|---|---|
| **Claude Code** | `./install.sh` (liga a pasta em `~/.claude/skills/re-copilot`) | testado |
| Claude Code, aviso automático | `./install.sh --hook <projeto>`: no início de cada sessão, avisa que fontes mudaram e quais requisitos as citam | testado |
| **Qualquer cliente MCP** | `./install.sh --motor` e `./install.sh --mcp` (mostra a configuração) | testado no Claude Code e com cliente stdio |
| Codex CLI | `./install.sh --codex` (bloco em `~/.codex/AGENTS.md`) | experimental |
| Gemini CLI | `./install.sh --gemini` (bloco em `~/.gemini/GEMINI.md`) | experimental |
| Cursor | `./install.sh --cursor <projeto>` (regra em `.cursor/rules/`) | experimental |
| Outro agente | `./install.sh --agents <arquivo de instruções>` | experimental |

A pasta do repositório é a própria skill: `SKILL.md` é o ponto de entrada. Qualquer agente que leia arquivos e rode
comandos consegue seguir o método. "Experimental" significa que o instalador funciona, mas o método ainda não foi
avaliado naquele agente (na 0.5, Codex e Gemini não rodaram por limitação das contas de teste, não da skill).

### Servidor MCP

```bash
claude mcp add re-copilot -- uv run --project "$PWD" --extra mcp --extra embeddings re-copilot-mcp
```

Oferece o prompt `re-copilot` (o método), as referências e os perfis como recursos, 20 ferramentas `re_*` (modelo,
checagens, rastreabilidade, baseline, exportação e publicação, vigilância de fontes, extração, esquema de banco,
leitura que oculta segredos) e 4 `rag_*` (indexar, buscar, construir, julgar contradições). Configuração para Codex e
Cursor: `./install.sh --mcp`.

## Uso

No diretório do projeto que você quer analisar, peça ao agente: **"re-copilot: o escopo é …"**. A skill cria `.re/`
no projeto, registra as fontes, diagnostica, faz as perguntas que faltam e gera os documentos em `.re/entregaveis/`.

Comandos úteis a qualquer momento: `status`, `diagnóstico`, `entrevistar financeiro`, `mudança: <texto>`,
`impacto RN-004`, `verificar`, `contradições`, `ler banco <dsn>`, `baseline`, `entregáveis`, `publicar no jira`.
Lista completa em [`SKILL.md`](SKILL.md).

### Integrações

| Com | Como | Credencial |
|---|---|---|
| Jira Cloud | `recop.py publicar jira [--aplicar] [--delta]` cria épicos e histórias e atualiza nas próximas vezes | `JIRA_URL`, `JIRA_EMAIL`, `JIRA_TOKEN`, `JIRA_PROJETO` |
| Azure DevOps | `recop.py publicar azure --processo agile [--aplicar]` cria Epic → Feature → User Story | `AZURE_DEVOPS_ORG`, `AZURE_DEVOPS_PROJETO`, `AZURE_DEVOPS_PAT` |
| PostgreSQL / MySQL / SQLite | `recop.py esquema <dsn>`: só a estrutura, conexão de leitura | `PGPASSWORD` / `MYSQL_PWD` (nunca no DSN) |
| docx, pptx, xlsx, csv | `recop.py extrair <arquivo>` transcreve para `.re/extraidos` | — |

Sem `--aplicar`, `publicar` só mostra o plano. As credenciais ficam no seu ambiente, nunca no chat ou em arquivo.

Para ver funcionando sem dados seus, use um dos casos em [`exemplos/`](exemplos), cada um com gabarito.

## RAG e provedores de LLM

O motor (`rag-re-engine`) indexa as fontes com embeddings multilíngues locais e usa LLM em algumas estratégias.
Escolha o provedor com `--llm` (padrão `auto`):

| `--llm` | Provedor |
|---|---|
| `claude` | Claude Code (`claude -p`), sem chave de API |
| `anthropic[:modelo]` | API da Anthropic (`uv sync --extra anthropic`) |
| `openai[:modelo]` | qualquer API compatível com OpenAI (`OPENAI_API_KEY`, `OPENAI_BASE_URL`) |
| `ollama[:modelo]` | Ollama local, sem custo de API (`RE_LLM_TIMEOUT` para modelos lentos em CPU) |
| `none` | sem LLM: as estratégias que dependem dele usam a busca simples, e o motor avisa |

Por padrão a skill **lê as fontes diretamente até 300 KB** e só usa o RAG acima disso, porque nas bases pequenas
testadas ele custou mais tempo sem melhorar a cobertura. Peça "use RAG" para forçar. A busca é híbrida: numa base de
600 documentos parecidos, a busca só vetorial achou o documento certo em 15% das consultas; a híbrida, em 87%. Todas as arquiteturas são
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

| 0.5: testes de funcionamento | Manutenção em 3 sessões, hook e MCP no Claude Code, banco PostgreSQL real, Ollama local achando contradição que a checagem léxica perdeu, escala de 600 documentos ([detalhes](docs/validacao/resultados/v05-funcionamento.md)) |

Ainda não provado: se a v4/v5 recuperou a cobertura (rodada 04), o uso por outras pessoas, a publicação contra um Jira
ou Azure DevOps de verdade (testada com API simulada) e o uso no Codex e no Gemini. Juízes e oráculos das rodadas são
IA, e cada condição rodou uma vez.

## Estrutura

```
SKILL.md          ponto de entrada do método
references/       workflow, modelo, fontes, diagnóstico, entrevista, manutenção, entregáveis, backlog, RAG
roles/            19 perfis e um modelo para perfis novos
scripts/recop.py  utilitário sem dependências: init, check, lint, verificar, render, impacto, pares, ligações,
                  vigiar, extrair, esquema, baseline, diff, exportar, publicar, ver
engine/           motor RAG e servidor MCP (pacote rag_re_engine); engine/benchmarks: teste de escala
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
