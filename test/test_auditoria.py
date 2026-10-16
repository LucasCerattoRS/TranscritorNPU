"""Auditoria: modelo que não carrega, título nulo do yt-dlp e entradas corrompidas (OCR/PDF)."""

import pytest

import app


def test_modelo_ausente_vira_erro_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MODELO", tmp_path / "nao existe")
    monkeypatch.setattr(app, "_pipelines", {})
    with pytest.raises(app.gr.Error, match="modelo"):
        app.obter_pipeline("CPU")


def test_modelo_ilegivel_vira_erro_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MODELO", tmp_path)
    monkeypatch.setattr(app, "_pipelines", {})

    def quebra(*a, **k):
        raise RuntimeError("Exception from src/inference: bad xml")

    monkeypatch.setattr(app.openvino_genai, "WhisperPipeline", quebra)
    with pytest.raises(app.gr.Error, match="CPU"):
        app.obter_pipeline("CPU")
    assert "CPU" not in app._pipelines


def test_titulo_nulo_do_ytdlp_usa_nome_padrao(tmp_path, monkeypatch):
    class FalsoYDL:
        def __init__(self, opcoes):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            return {"title": None}

        def prepare_filename(self, info):
            return str(tmp_path / "x.webm")

    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", FalsoYDL)
    monkeypatch.setattr(app.Path, "exists", lambda self: False)
    _, titulo = app.baixar_de_url("https://exemplo.invalid", str(tmp_path), lambda *a, **k: None)
    assert titulo == "audio_url"


def test_imagem_corrompida_vira_erro_claro(monkeypatch):
    def quebra(*a, **k):
        raise OSError("cannot identify image file")

    monkeypatch.setattr(app.Image, "open", quebra)
    with pytest.raises(app.gr.Error, match="imagem"):
        app.transcrever_imagem("lixo.png", "Português")


def test_pdf_corrompido_vira_erro_claro(monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("cannot open broken document")

    monkeypatch.setattr(app.fitz, "open", quebra)
    with pytest.raises(app.gr.Error, match="PDF"):
        app.transcrever_pdf("lixo.pdf", "Português")
