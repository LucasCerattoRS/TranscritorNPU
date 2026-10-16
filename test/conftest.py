"""Stubs das dependências pesadas, instalados antes de qualquer teste importar `app`.

gradio vira um MagicMock com `Error` de verdade (subclasse de Exception), para que
`raise gr.Error(...)` funcione e os testes possam verificar a mensagem.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _ErroGradio(Exception):
    pass


_gradio = MagicMock()
_gradio.Error = _ErroGradio
sys.modules.setdefault("gradio", _gradio)

for _mod in ("openvino_genai", "fitz", "pytesseract", "yt_dlp", "PIL"):
    sys.modules.setdefault(_mod, MagicMock())
