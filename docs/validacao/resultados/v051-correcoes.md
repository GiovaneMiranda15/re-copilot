# Correções da 0.5.1 (24/11/2026)

## Contradições

`engine/benchmarks/contradicoes.py`: 36 pares rotulados (16 contradições, 12 complementares, 8 independentes; 13 são armadilhas).
Dados: `contradicoes-05.json`.

| Detector | Precisão | Recall | F1 | Recall nas de sentido | Armadilhas apontadas | Tempo |
|---|---|---|---|---|---|---|
| `recop.py pares` (léxico, sem LLM) | 0,50 | 0,25 | 0,33 | 0,20 | 4 de 13 | imediato |
| `contradicoes`, qwen3:4b local em CPU | 1,00 | 0,94 | 0,97 | 0,90 | 0 de 13 | 1.114 s |
| `contradicoes`, Claude Haiku | 0,94 | 1,00 | 0,97 | 1,00 | 1 de 13 | 57 s |
| `contradicoes`, Claude Sonnet | 1,00 | 1,00 | 1,00 | 1,00 | 0 de 13 | 39 s |

Com os 72 requisitos num só projeto, há 2.556 pares possíveis e `pares --amplo` seleciona 196. Recall das contradições reais: 0,94 nos 60
primeiros, 0,94 nos 120 primeiros e 1,00 em todos. Ou seja, o limite padrão de 60 **perde uma em 16**; `-n 0` não perde.

Leitura:
- A lista léxica é fraca para decidir: erra metade do que aponta e perde três de cada quatro. Sirva-se dela só como indício.
- Os modelos batem no teto. Os pares são curtos, explícitos e **escritos por quem fez a ferramenta**; requisitos reais, longos e com
  condições, devem dar resultado pior. Não use estes números como medida de qualidade em campo.
- `recall` de candidatos 1,00 também depende dos textos: contradição sem nenhuma palavra em comum não vira candidata.

## Banco ao vivo

| Servidor | Como | Resultado |
|---|---|---|
| MySQL 8.4 (Docker, com dados) | cliente do contêiner | tabelas, FK, CHECK, comentário, view, trigger, rotina e evento; nenhum dado; saída idêntica em duas execuções |
| MariaDB 11.4 (Docker, com dados) | `mariadb-dump` | tabelas, view, rotina; nenhum dado |
| PostgreSQL 16 (Docker, com dados) | `pg_dump` | função com `UPDATE … SET` preservada |
| Usuário só com `SELECT` (MySQL) | — | recusa e explica as permissões que faltam |

Defeito grave corrigido: no PostgreSQL, toda linha iniciada por `SET ` era apagada, inclusive dentro de função. Um `UPDATE pedido / SET
status = 'bloqueado'` perdia a cláusula, e a regra de negócio extraída ficava errada. Afeta quem extraiu com a 0.5.0.
