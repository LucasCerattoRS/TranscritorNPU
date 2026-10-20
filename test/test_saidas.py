"""Regressões de preservação dos arquivos de saída, com conteúdo sintético."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import app


@pytest.mark.parametrize("origem", ["audio", "url", "imagem", "pdf"])
@pytest.mark.parametrize("nome", ["entrada", "🎵" * 60], ids=["curto", "unicode_longo"])
def test_extracoes_no_mesmo_segundo_preservam_os_dois_resultados(tmp_path, monkeypatch, origem, nome):
    class RelogioFixo:
        @staticmethod
        def now():
            return datetime(2026, 1, 1, 12)

    monkeypatch.setattr(app, "datetime", RelogioFixo)
    monkeypatch.setattr(app, "SAIDAS", tmp_path)
    textos = iter(["primeira extração", "segunda extração"])

    if origem in ("audio", "url"):
        class Resultado:
            chunks = [SimpleNamespace(start_ts=0, end_ts=1, text="legenda")]

            def __str__(self):
                return next(textos)

        pipe = MagicMock()
        pipe.generate.side_effect = lambda *a: Resultado()
        monkeypatch.setattr(app, "obter_pipeline", lambda *a: pipe)
        monkeypatch.setattr(app, "carregar_audio", lambda *a: np.zeros(16000))

        monkeypatch.setattr(app, "baixar_de_url", lambda *a: ("baixado.wav", nome))

        def extrair():
            if origem == "url":
                texto, caminhos, _ = app.transcrever(None, "https://exemplo.invalid", "CPU", "Português")
            else:
                texto, caminhos, _ = app.transcrever(f"{nome}.wav", "", "CPU", "Português")
            return texto, list(map(Path, caminhos))
    else:
        if origem == "imagem":
            monkeypatch.setattr(app.Image, "open", lambda *a: MagicMock())
            monkeypatch.setattr(app.pytesseract, "image_to_string", lambda *a, **k: next(textos))
            funcao, entrada = app.transcrever_imagem, f"{nome}.png"
        else:
            doc = MagicMock()
            doc.page_count = 1
            doc.__iter__.side_effect = lambda: iter([SimpleNamespace(get_text=lambda: next(textos))])
            monkeypatch.setattr(app.fitz, "open", lambda *a: doc)
            funcao, entrada = app.transcrever_pdf, f"{nome}.pdf"

        def extrair():
            texto, caminho = funcao(entrada, "Português")
            return texto, [Path(caminho)]

    texto1, caminhos1 = extrair()
    conteudos1 = [p.read_text(encoding="utf-8") for p in caminhos1]
    texto2, caminhos2 = extrair()

    assert texto1 != texto2
    assert set(caminhos1).isdisjoint(caminhos2)
    assert [p.read_text(encoding="utf-8") for p in caminhos1] == conteudos1
    assert caminhos2[0].read_text(encoding="utf-8") == texto2
