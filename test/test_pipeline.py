"""Concorrência e recuperação do cache sem carregar modelos reais."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import app


def test_cargas_concorrentes_compartilham_um_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MODELO", tmp_path)
    monkeypatch.setattr(app, "_pipelines", {})
    primeira_carga = Event()
    carga_duplicada = Event()
    liberar = Event()
    segunda_chamada = Event()

    def construir(*a, **k):
        if primeira_carga.is_set():
            carga_duplicada.set()
        primeira_carga.set()
        assert liberar.wait(5), "a carga simulada não foi liberada"
        return object()

    def obter_segundo():
        segunda_chamada.set()
        return app.obter_pipeline("CPU")

    monkeypatch.setattr(app.openvino_genai, "WhisperPipeline", construir)
    with ThreadPoolExecutor(max_workers=2) as executor:
        primeira = executor.submit(app.obter_pipeline, "CPU")
        try:
            assert primeira_carga.wait(5)
            segunda = executor.submit(obter_segundo)
            assert segunda_chamada.wait(5)
            carga_duplicada.wait(0.2)
        finally:
            liberar.set()
        pipe1, pipe2 = primeira.result(timeout=5), segunda.result(timeout=5)

    assert pipe1 is pipe2
    assert app.obter_pipeline("CPU") is pipe1
