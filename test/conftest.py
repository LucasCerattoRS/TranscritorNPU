"""Stubs das dependências pesadas, instalados antes de qualquer teste importar `app`.

gradio vira um MagicMock com `Error` de verdade (subclasse de Exception), para que
`raise gr.Error(...)` funcione e os testes possam verificar a mensagem.
"""

import os
import sys
import types
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _ErroGradio(Exception):
    pass


_gradio = MagicMock()
_gradio.Error = _ErroGradio
sys.modules.setdefault("gradio", _gradio)

# Módulos com os atributos que o app usa declarados de verdade. Um MagicMock puro cria atributos
# só sob demanda, e o monkeypatch.setattr do pytest recente recusa trocar atributo que "não existe"
# (era a causa das 8 falhas no CI: fitz.open, Image.open, WhisperPipeline...).
def _modulo(nome, **attrs):
    mod = types.ModuleType(nome)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


_image = _modulo("PIL.Image", open=MagicMock(), frombytes=MagicMock())
_stubs = {
    "openvino_genai": _modulo("openvino_genai", WhisperPipeline=MagicMock()),
    "fitz": _modulo("fitz", open=MagicMock()),
    "pytesseract": _modulo("pytesseract", image_to_string=MagicMock(), pytesseract=MagicMock()),
    "yt_dlp": _modulo("yt_dlp", YoutubeDL=MagicMock(), utils=MagicMock(), cookies=MagicMock()),
    "PIL": _modulo("PIL", Image=_image),
    "PIL.Image": _image,
}
for _nome, _mod in _stubs.items():
    sys.modules.setdefault(_nome, _mod)
