#!/usr/bin/env bash
# Instala o re-copilot no seu agente. A pasta deste repositório é a própria skill.
#
#   ./install.sh                      Claude Code: ~/.claude/skills/re-copilot (symlink para esta pasta)
#   ./install.sh --copia              Claude Code, copiando em vez de ligar
#   ./install.sh --codex              Codex CLI: bloco de instruções em ~/.codex/AGENTS.md
#   ./install.sh --gemini             Gemini CLI: bloco de instruções em ~/.gemini/GEMINI.md
#   ./install.sh --cursor <projeto>   Cursor: regra em <projeto>/.cursor/rules/re-copilot.mdc
#   ./install.sh --agents <arquivo>   qualquer agente que leia um arquivo de instruções (AGENTS.md etc.)
#   ./install.sh --motor              instala as dependências do motor RAG e do servidor MCP (uv sync)
#   ./install.sh --mcp                mostra como registrar o servidor MCP nos clientes
#
# Os blocos de instruções ficam entre marcadores e são substituídos ao reinstalar.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INICIO="<!-- re-copilot:inicio -->"
FIM="<!-- re-copilot:fim -->"

bloco() {
  cat <<TXT
$INICIO
## re-copilot (Engenharia de Requisitos)

Quando o usuário pedir para levantar, elicitar, diagnosticar, especificar, validar ou manter requisitos, avaliar o
impacto de uma mudança, gerar backlog ou digitar "re-copilot": leia \`$SRC/SKILL.md\` e siga o método. Nesse
arquivo, \`<skill>\` é \`$SRC\`. Leia as referências e os perfis sob demanda. Se o servidor MCP \`re-copilot\` estiver
configurado, prefira as ferramentas \`re_*\` e \`rag_*\` aos comandos de terminal equivalentes.
$FIM
TXT
}

grava_bloco() {
  local destino="$1"
  mkdir -p "$(dirname "$destino")"
  touch "$destino"
  RE_BLOCO="$(bloco)" python3 - "$destino" "$INICIO" "$FIM" <<'PY'
import os, re, sys
destino, ini, fim = sys.argv[1:4]
novo = os.environ["RE_BLOCO"].strip()
texto = open(destino).read()
padrao = re.compile(re.escape(ini) + ".*?" + re.escape(fim), re.S)
texto = padrao.sub(lambda _: novo, texto) if padrao.search(texto) else (texto.rstrip() + "\n\n" + novo + "\n").lstrip()
open(destino, "w").write(texto)
PY
  echo "instruções gravadas em $destino"
}

claude() {
  local dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/re-copilot"
  if [ -L "$dest" ] && [ "$(readlink -f "$dest")" = "$SRC" ]; then
    echo "já instalado: $dest -> $SRC"
    return
  fi
  if [ -e "$dest" ]; then
    echo "já existe $dest; remova ou mova antes de reinstalar" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$dest")"
  if [ "${1:-}" = copia ]; then
    (cd "$SRC" && tar --exclude=.git --exclude=.venv --exclude=__pycache__ --exclude='*.db' -cf - .) | (mkdir -p "$dest" && cd "$dest" && tar -xf -)
    echo "skill copiada para $dest"
  else
    ln -s "$SRC" "$dest"
    echo "skill ligada: $dest -> $SRC"
  fi
  echo "reinicie o Claude Code e digite: re-copilot"
}

mcp_ajuda() {
  cat <<TXT
Servidor MCP: re-copilot-mcp (stdio). Comando para os clientes:
  uv run --project "$SRC" --extra mcp --extra embeddings re-copilot-mcp

Claude Code:  claude mcp add re-copilot -- uv run --project "$SRC" --extra mcp --extra embeddings re-copilot-mcp
Codex CLI (~/.codex/config.toml):
  [mcp_servers.re-copilot]
  command = "uv"
  args = ["run", "--project", "$SRC", "--extra", "mcp", "--extra", "embeddings", "re-copilot-mcp"]
Cursor e outros clientes com mcp.json:
  {"mcpServers": {"re-copilot": {"command": "uv", "args": ["run", "--project", "$SRC", "--extra", "mcp", "--extra", "embeddings", "re-copilot-mcp"]}}}
TXT
}

case "${1:-}" in
  "") claude ;;
  --copia) claude copia ;;
  --codex) grava_bloco "${CODEX_HOME:-$HOME/.codex}/AGENTS.md" ;;
  --gemini) grava_bloco "$HOME/.gemini/GEMINI.md" ;;
  --cursor)
    [ -n "${2:-}" ] || { echo "uso: ./install.sh --cursor <pasta do projeto>" >&2; exit 2; }
    regra="$2/.cursor/rules/re-copilot.mdc"
    mkdir -p "$(dirname "$regra")"
    { printf -- '---\ndescription: re-copilot, Engenharia de Requisitos\nalwaysApply: false\n---\n'; bloco; } >"$regra"
    echo "regra gravada em $regra" ;;
  --agents)
    [ -n "${2:-}" ] || { echo "uso: ./install.sh --agents <arquivo de instruções>" >&2; exit 2; }
    grava_bloco "$2" ;;
  --motor)
    command -v uv >/dev/null || { echo "uv não encontrado: https://docs.astral.sh/uv/" >&2; exit 1; }
    (cd "$SRC" && uv sync --extra embeddings --extra mcp)
    echo "motor pronto: uv run --project \"$SRC\" rag-re-engine --help" ;;
  --mcp) mcp_ajuda ;;
  *) sed -n '2,13p' "$0"; exit 2 ;;
esac
