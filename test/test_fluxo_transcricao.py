"""Testes do fluxo de transcrição do app.py com stubs: sem NPU, sem modelo, sem ffmpeg, sem rede."""

import types

import numpy as np
import pytest

import app


class _Chunk:
    def __init__(self, start_ts, end_ts, text):
        self.start_ts, self.end_ts, self.text = start_ts, end_ts, text


class _Resultado:
    def __init__(self, texto, chunks):
        self._texto, self.chunks = texto, chunks

    def __str__(self):
        return self._texto


class _PipelineFalso:
    def __init__(self, resultado):
        self._resultado = resultado

    def get_generation_config(self):
        return types.SimpleNamespace()

    def generate(self, audio, config):
        return self._resultado


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Redireciona saídas pra pasta temporária e troca decodificação/modelo por falsos."""
    saidas = tmp_path / "saidas"
    saidas.mkdir()
    monkeypatch.setattr(app, "SAIDAS", saidas)
    monkeypatch.setattr(app, "carregar_audio", lambda caminho: np.zeros(16000, dtype=np.float32))
    resultado = _Resultado("olá, tudo bem?", [_Chunk(0, 1, "olá, tudo bem?")])
    monkeypatch.setattr(app, "obter_pipeline", lambda disp: _PipelineFalso(resultado))
    return saidas


def test_nome_com_acento_gera_saidas_com_o_mesmo_nome(ambiente):
    texto, arquivos, _ = app.transcrever("/tmp/Reunião São João ção.mp3", "", "CPU", "Português")
    assert texto == "olá, tudo bem?"
    por_extensao = {p.rsplit(".", 1)[-1]: p for p in arquivos}
    assert set(por_extensao) == {"txt", "srt"}
    for caminho in por_extensao.values():
        assert caminho.rsplit("/", 1)[-1].startswith("Reunião São João ção_")
    assert "olá" in (ambiente / por_extensao["srt"].rsplit("/", 1)[-1]).read_text(encoding="utf-8")


def test_falha_no_download_limpa_a_pasta_temporaria(ambiente, monkeypatch):
    criadas = []
    real = app.tempfile.TemporaryDirectory

    def espiao(*a, **k):
        d = real(*a, **k)
        criadas.append(d)
        return d

    def baixar_falha(url, pasta, progress):
        raise app.gr.Error("sem rede")

    monkeypatch.setattr(app.tempfile, "TemporaryDirectory", espiao)
    monkeypatch.setattr(app, "baixar_de_url", baixar_falha)

    with pytest.raises(app.gr.Error):
        app.transcrever(None, "https://exemplo.invalid/v", "CPU", "Português")

    assert len(criadas) == 1
    import os
    assert not os.path.exists(criadas[0].name), "pasta temporária do download vazou"


def test_ffmpeg_ausente_vira_erro_claro(monkeypatch):
    def sem_ffmpeg(*a, **k):
        raise FileNotFoundError(2, "No such file or directory: 'ffmpeg'")

    monkeypatch.setattr(app.subprocess, "run", sem_ffmpeg)
    with pytest.raises(app.gr.Error, match="ffmpeg"):
        app.carregar_audio("qualquer.mp3")


def test_srt_ignora_trechos_vazios_e_renumera():
    srt = app.gerar_srt([_Chunk(0, 1, "um"), _Chunk(1, 2, "   "), _Chunk(2, 3, "dois")])
    assert srt.startswith("1\n")
    assert "\n2\n00:00:02,000 --> 00:00:03,000\ndois" in srt
    assert srt.count("-->") == 2
