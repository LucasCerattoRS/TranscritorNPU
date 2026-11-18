"""(Cópia adaptada de ~/Projetos/video-downloader/historico.py.)
Histórico de downloads gravado em disco, para sobreviver a um reinício do servidor.

Um arquivo JSON por usuário (não fica dentro da pasta do app, que pode estar no pendrive
ou num repositório Git):
  Linux/macOS: ~/.local/share/transcritor-npu/historico.json  (ou $XDG_DATA_HOME)
  Windows:     %APPDATA%\\transcritor-npu\\historico.json
TRANSCRITOR_HISTORICO=/caminho/arquivo.json troca o local (usado nos testes).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

LIMITE = 200  # itens mais recentes guardados; o resto é descartado


def caminho_padrao() -> str:
    if os.environ.get("TRANSCRITOR_HISTORICO"):
        return os.environ["TRANSCRITOR_HISTORICO"]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "transcritor-npu", "historico.json")


def carregar(caminho: str, ativos=frozenset()) -> list[dict]:
    """Lê o histórico. Arquivo ausente ou ilegível = histórico vazio (nunca derruba o servidor).

    Jobs que estavam na fila ou baixando quando o servidor parou não vão continuar
    (a fila vive na memória): voltam marcados como interrompidos. `ativos` são os ids
    que ESTE processo ainda está baixando: esses não são interrompidos (senão recarregar
    a página ou começar um segundo download marcaria o primeiro como interrompido).
    """
    try:
        with open(caminho, encoding="utf-8") as f:
            itens = json.load(f)
    except (OSError, ValueError, RecursionError):  # RecursionError: JSON aninhado demais
        return []
    if not isinstance(itens, list):
        return []
    validos = []
    for item in itens:
        if not isinstance(item, dict) or "id" not in item:
            continue
        if item.get("status") in ("queued", "downloading") and not (
                isinstance(item["id"], str) and item["id"] in ativos):
            item["status"] = "error"
            item["error"] = "Interrompido: o servidor foi reiniciado."
        validos.append(item)
    return validos[:LIMITE]


def salvar(caminho: str, itens: list[dict]) -> None:
    """Grava de forma atômica (arquivo temporário + rename): uma queda no meio não corrompe."""
    pasta = os.path.dirname(caminho) or "."
    os.makedirs(pasta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=pasta, prefix=".historico-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(itens[:LIMITE], f, ensure_ascii=False, indent=1)
        os.replace(tmp, caminho)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
