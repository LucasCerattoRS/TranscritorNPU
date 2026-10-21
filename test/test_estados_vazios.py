"""Casos negativos que já devem ser tratados sem criar saídas ou engolir erros."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app


@pytest.mark.parametrize("origem", ["audio", "imagem", "pdf"])
def test_entrada_ausente_nao_cria_saida(tmp_path, monkeypatch, origem):
    monkeypatch.setattr(app, "SAIDAS", tmp_path)
    with pytest.raises(app.gr.Error):
        if origem == "audio":
            app.transcrever(None, "", "CPU", "Português")
        elif origem == "imagem":
            app.transcrever_imagem(None, "Português")
        else:
            app.transcrever_pdf(None, "Português")
    assert list(tmp_path.iterdir()) == []


def test_ffmpeg_sem_amostras_rejeita_audio_vazio(monkeypatch):
    monkeypatch.setattr(app.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=b"", stderr=b""
    ))
    with pytest.raises(app.gr.Error, match="não contém áudio"):
        app.carregar_audio("vazio.wav")


def test_pdf_sem_paginas_nao_cria_saida(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAIDAS", tmp_path)
    doc = MagicMock()
    doc.page_count = 0
    doc.__iter__.return_value = iter([])
    monkeypatch.setattr(app.fitz, "open", lambda *a: doc)
    with pytest.raises(app.gr.Error, match="Nenhum texto"):
        app.transcrever_pdf("vazio.pdf", "Português")
    assert list(tmp_path.iterdir()) == []


def test_erro_de_geracao_comum_e_propagado_sem_retry(monkeypatch):
    pipe = MagicMock()
    erro = RuntimeError("falha de inferência")
    pipe.generate.side_effect = erro
    monkeypatch.setattr(app, "obter_pipeline", lambda *a: pipe)
    with pytest.raises(RuntimeError) as exc:
        app._gerar_com_retry("CPU", [], object())
    assert exc.value is erro
    assert pipe.generate.call_count == 1


def test_device_lost_invalida_o_cache_e_repete_uma_vez(monkeypatch):
    antigo, novo = MagicMock(), MagicMock()
    antigo.generate.side_effect = RuntimeError("DEVICE_LOST")
    novo.generate.return_value = "transcrição recuperada"
    monkeypatch.setattr(app, "_pipelines", {"CPU": antigo})
    monkeypatch.setattr(app, "MODELO", MagicMock(is_dir=lambda: True))
    monkeypatch.setattr(app.openvino_genai, "WhisperPipeline", lambda *a, **k: novo)
    assert app._gerar_com_retry("CPU", [], object()) == "transcrição recuperada"
    assert app.obter_pipeline("CPU") is novo


def test_segundo_device_lost_e_propagado(monkeypatch):
    antigo, novo = MagicMock(), MagicMock()
    antigo.generate.side_effect = RuntimeError("DEVICE_LOST")
    erro = RuntimeError("DEVICE_LOST novamente")
    novo.generate.side_effect = erro
    monkeypatch.setattr(app, "_pipelines", {"CPU": antigo})
    monkeypatch.setattr(app, "MODELO", MagicMock(is_dir=lambda: True))
    monkeypatch.setattr(app.openvino_genai, "WhisperPipeline", lambda *a, **k: novo)
    with pytest.raises(RuntimeError) as exc:
        app._gerar_com_retry("CPU", [], object())
    assert exc.value is erro
    assert novo.generate.call_count == 1
