"""Onde estão os arquivos da skill e qual `recop.py` usar.

No repositório (inclusive na instalação editável, `uv run --project`), vale `scripts/recop.py` da pasta: a cópia
que a instalação editável põe no ambiente fica velha depois de um `git pull`. Instalado como wheel, vale o módulo
`recop` empacotado e a cópia da skill em `rag_re_engine/skill`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_RECOP = None


def pasta_skill() -> Path:
    empacotada = Path(__file__).resolve().parent / "skill"
    if (empacotada / "SKILL.md").exists():
        return empacotada
    return Path(__file__).resolve().parents[3]


def recop():
    global _RECOP
    if _RECOP is None:
        arquivo = Path(__file__).resolve().parents[3] / "scripts" / "recop.py"
        if arquivo.exists():
            spec = importlib.util.spec_from_file_location("recop", arquivo)
            _RECOP = importlib.util.module_from_spec(spec)
            sys.modules["recop"] = _RECOP
            spec.loader.exec_module(_RECOP)
        else:
            import recop as modulo
            _RECOP = modulo
    return _RECOP


def recop_main() -> int:
    return recop().main()
