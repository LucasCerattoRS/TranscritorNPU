"""Testes das funções puras de SRT do app.py, SEM tocar no código do app.

Estratégia: as dependências pesadas (gradio, openvino, fitz, pytesseract, PIL,
yt_dlp) não estão instaladas nesta máquina — e não precisam estar pra testar
a formatação de legenda. Stubamos elas em sys.modules com MagicMock antes de
importar `app`, então `_ts_srt`/`gerar_srt` testados são o código REAL.

Rodar: pytest -q   (ou: python test/test_srt.py)
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _mod in ("gradio", "openvino_genai", "fitz", "pytesseract", "yt_dlp", "PIL"):
    sys.modules.setdefault(_mod, MagicMock())

import app  # noqa: E402  (import tardio de propósito, depois dos stubs)


def test_ts_srt_zero():
    assert app._ts_srt(0) == "00:00:00,000"


def test_ts_srt_subsecond_uses_comma():
    # SRT usa vírgula como separador decimal, não ponto
    assert app._ts_srt(1.5) == "00:00:01,500"


def test_ts_srt_minutes_and_seconds():
    assert app._ts_srt(61.5) == "00:01:01,500"


def test_ts_srt_hours_overflow():
    # 2h 2m 5.25s — horas com dois dígitos, sem estourar pra 60
    assert app._ts_srt(7325.25) == "02:02:05,250"


def test_ts_srt_rounds_to_millis():
    assert app._ts_srt(3.1239) == "00:00:03,124"


def test_ts_srt_rounding_never_gives_60_seconds():
    # 59.9996 s arredonda pra 1 min cheio; antes saía "00:00:60,000" (SRT inválido)
    assert app._ts_srt(59.9996) == "00:01:00,000"
    assert app._ts_srt(3599.9999) == "01:00:00,000"


def test_nome_seguro_remove_caracteres_proibidos_no_windows():
    # título de vídeo vira nome de arquivo; ':' '?' '/' quebram write_text no Windows
    assert app._nome_seguro('Live: "Ao vivo"? 1/2') == "Live_ _Ao vivo__ 1_2"
    assert app._nome_seguro("   ") == "transcricao"


class _Chunk:
    def __init__(self, start_ts, end_ts, text):
        self.start_ts, self.end_ts, self.text = start_ts, end_ts, text


def test_gerar_srt_numbers_and_arrows():
    srt = app.gerar_srt([_Chunk(0, 1.5, "  olá  "), _Chunk(1.5, 3, "mundo")])
    assert "1\n00:00:00,000 --> 00:00:01,500\nolá\n" in srt   # texto é trimado
    assert "2\n00:00:01,500 --> 00:00:03,000\nmundo\n" in srt


def test_gerar_srt_empty():
    assert app.gerar_srt([]) == ""


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
