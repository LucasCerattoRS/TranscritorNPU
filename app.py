# -*- coding: utf-8 -*-
"""Transcritor NPU — Whisper large-v3-turbo via OpenVINO com interface Gradio.

Dispositivos: NPU (Intel AI Boost), GPU (Arc integrada) ou CPU.
Aceita qualquer áudio ou vídeo que o ffmpeg leia.
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import gradio as gr
import openvino_genai

PASTA = Path(__file__).parent
MODELO = PASTA / "modelo"
SAIDAS = PASTA / "saidas"
CACHE = PASTA / "cache"
SAIDAS.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

IDIOMAS = {
    "Detectar automaticamente": "auto",
    "Português": "pt",
    "Inglês": "en",
    "Espanhol": "es",
    "Francês": "fr",
    "Alemão": "de",
    "Italiano": "it",
    "Japonês": "ja",
}

# Pipelines já carregados, um por dispositivo (carregar na NPU leva ~1 min na primeira vez)
_pipelines = {}


def obter_pipeline(dispositivo: str) -> openvino_genai.WhisperPipeline:
    if dispositivo not in _pipelines:
        _pipelines[dispositivo] = openvino_genai.WhisperPipeline(str(MODELO), dispositivo, CACHE_DIR=str(CACHE))
    return _pipelines[dispositivo]


def carregar_audio(caminho: str) -> np.ndarray:
    """Decodifica qualquer áudio/vídeo para PCM float32 mono 16 kHz via ffmpeg."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", caminho,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise gr.Error("ffmpeg não conseguiu ler o arquivo: " + proc.stderr.decode(errors="replace")[:500])
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise gr.Error("O arquivo não contém áudio.")
    return audio


def _ts_srt(segundos: float) -> str:
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def gerar_srt(chunks) -> str:
    blocos = []
    for i, c in enumerate(chunks, 1):
        blocos.append(f"{i}\n{_ts_srt(c.start_ts)} --> {_ts_srt(c.end_ts)}\n{c.text.strip()}\n")
    return "\n".join(blocos)


def transcrever(arquivo, dispositivo, idioma_nome, progress=gr.Progress()):
    if not arquivo:
        raise gr.Error("Envie um arquivo de áudio ou vídeo primeiro.")

    progress(0.05, desc="Decodificando áudio…")
    audio = carregar_audio(arquivo)
    duracao = audio.size / 16000

    progress(0.15, desc=f"Carregando modelo em {dispositivo}… (a primeira vez demora)")
    pipe = obter_pipeline(dispositivo)

    config = pipe.get_generation_config()
    config.task = "transcribe"
    config.return_timestamps = True
    codigo = IDIOMAS.get(idioma_nome, "auto")
    if codigo != "auto":
        config.language = f"<|{codigo}|>"

    progress(0.3, desc=f"Transcrevendo {duracao/60:.1f} min de áudio em {dispositivo}…")
    inicio = time.time()
    resultado = pipe.generate(audio, config)
    tempo = time.time() - inicio

    texto = str(resultado).strip()
    carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = Path(arquivo).stem[:60]

    arq_txt = SAIDAS / f"{base}_{carimbo}.txt"
    arq_txt.write_text(texto, encoding="utf-8")
    arquivos = [str(arq_txt)]

    if resultado.chunks:
        arq_srt = SAIDAS / f"{base}_{carimbo}.srt"
        arq_srt.write_text(gerar_srt(resultado.chunks), encoding="utf-8")
        arquivos.append(str(arq_srt))

    fator = duracao / tempo if tempo > 0 else 0
    info = (
        f"Áudio: {duracao/60:.1f} min · Dispositivo: {dispositivo} · "
        f"Tempo: {tempo:.1f} s · Velocidade: {fator:.1f}× tempo real"
    )
    return texto, arquivos, info


with gr.Blocks(title="Transcritor NPU") as app:
    gr.Markdown("# 🎙️ Transcritor NPU\nWhisper large-v3-turbo rodando localmente no seu Intel Core Ultra.")
    with gr.Row():
        with gr.Column(scale=1):
            entrada = gr.File(label="Áudio ou vídeo", file_types=["audio", "video"], type="filepath")
            dispositivo = gr.Dropdown(["NPU", "GPU", "CPU"], value="NPU", label="Dispositivo")
            idioma = gr.Dropdown(list(IDIOMAS), value="Português", label="Idioma")
            botao = gr.Button("Transcrever", variant="primary")
        with gr.Column(scale=2):
            texto = gr.Textbox(label="Transcrição", lines=18, buttons=["copy"])
            downloads = gr.File(label="Baixar (.txt / .srt)", file_count="multiple")
            info = gr.Markdown()
    botao.click(transcrever, [entrada, dispositivo, idioma], [texto, downloads, info])

if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", inbrowser=True)
