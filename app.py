# -*- coding: utf-8 -*-
"""Transcritor NPU — Whisper large-v3-turbo via OpenVINO com interface Gradio.

Dispositivos: NPU (Intel AI Boost), GPU (Arc integrada) ou CPU.
Aceita qualquer áudio ou vídeo que o ffmpeg leia (arquivo ou link via yt-dlp)
e imagens (OCR via Tesseract).
"""

import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import gradio as gr
import openvino_genai
import pytesseract
import yt_dlp
from PIL import Image

PASTA = Path(__file__).parent
MODELO = PASTA / "modelo"
SAIDAS = PASTA / "saidas"
CACHE = PASTA / "cache"
SAIDAS.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

# No Linux (`sudo dnf install tesseract`) o binário já cai no PATH e o pytesseract
# acha sozinho. No Windows, o `winget install UB-Mannheim.TesseractOCR` não
# registra no PATH por padrão, então só fixamos o caminho ali se for preciso.
if sys.platform == "win32" and shutil.which("tesseract") is None:
    caminho_padrao = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if caminho_padrao.exists():
        pytesseract.pytesseract.tesseract_cmd = str(caminho_padrao)

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

IDIOMAS_OCR = {
    "Português": "por",
    "Inglês": "eng",
    "Português + Inglês": "por+eng",
}

# Pipelines já carregados, um por dispositivo (carregar na NPU leva ~1 min na primeira vez)
_pipelines = {}


def obter_pipeline(dispositivo: str) -> openvino_genai.WhisperPipeline:
    if dispositivo not in _pipelines:
        _pipelines[dispositivo] = openvino_genai.WhisperPipeline(str(MODELO), dispositivo, CACHE_DIR=str(CACHE))
    return _pipelines[dispositivo]


def invalidar_pipeline(dispositivo: str) -> None:
    _pipelines.pop(dispositivo, None)


def _gerar_com_retry(dispositivo: str, audio: np.ndarray, config):
    """A NPU da Intel trava esporadicamente em uso repetido (bug conhecido do
    driver/OpenVINO, https://github.com/openvinotoolkit/openvino/issues/29386),
    deixando o pipeline em cache com um handle morto pro dispositivo. Quando
    isso acontece, descarta o pipeline e tenta de novo com um novo, já que o
    dispositivo em si costuma voltar a funcionar sozinho."""
    pipe = obter_pipeline(dispositivo)
    try:
        return pipe.generate(audio, config)
    except RuntimeError as e:
        if "DEVICE_LOST" not in str(e):
            raise
        invalidar_pipeline(dispositivo)
        return obter_pipeline(dispositivo).generate(audio, config)


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


def baixar_de_url(url: str, pasta_tmp: str, progress: gr.Progress) -> tuple[str, str]:
    """Baixa só a faixa de áudio de uma URL (YouTube etc.) via yt-dlp, sem baixar o vídeo inteiro."""

    def avisar(d):
        if d["status"] == "downloading":
            pct = d.get("_percent_str", "").strip()
            progress(0.1, desc=f"Baixando áudio da URL… {pct}")

    opcoes = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(pasta_tmp) / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [avisar],
        # YouTube exige resolver desafios JS pra liberar os formatos completos;
        # usa o Node.js já instalado na máquina em vez do runtime Deno padrão do yt-dlp.
        "js_runtimes": {"node": {}},
    }

    # Instagram (e outros sites logados) exigem sessão autenticada. Ordem de preferência:
    #  1) cookies.txt (formato Netscape) ao lado do app.py — rota mais confiável no
    #     Windows: funciona com o Brave aberto e mesmo com App-Bound Encryption, pois a
    #     exportação acontece dentro do navegador já logado (via extensão "Get cookies.txt").
    #  2) cookiesfrombrowser("brave") — só funciona com o Brave FECHADO e sem ABE.
    #  3) sem cookies — YouTube e URLs sem login seguem funcionando; conteúdo de IG
    #     que exige sessão vai falhar com "empty media response".
    cookies_txt = Path(__file__).with_name("cookies.txt")
    if cookies_txt.exists():
        opcoes["cookiefile"] = str(cookies_txt)
        print(f"[cookies] usando {cookies_txt.name}")
    else:
        try:
            yt_dlp.cookies.extract_cookies_from_browser("brave")
            opcoes["cookiesfrombrowser"] = ("brave",)
            print("[cookies] Brave OK")
        except Exception as e:
            print(f"[aviso] sem cookies (Brave indisponível), seguindo sem login: {e}")

    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = ydl.extract_info(url, download=True)
            caminho = ydl.prepare_filename(info)
    except Exception as e:
        raise gr.Error(f"Não consegui baixar o áudio dessa URL: {e}")
    return caminho, info.get("title", "audio_url")


def _ts_srt(segundos: float) -> str:
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def gerar_srt(chunks) -> str:
    blocos = []
    for i, c in enumerate(chunks, 1):
        blocos.append(f"{i}\n{_ts_srt(c.start_ts)} --> {_ts_srt(c.end_ts)}\n{c.text.strip()}\n")
    return "\n".join(blocos)


def transcrever(arquivo, url, dispositivo, idioma_nome, progress=gr.Progress()):
    if not arquivo and not url:
        raise gr.Error("Envie um arquivo de áudio/vídeo ou cole um link primeiro.")

    tmpdir = None
    base = None
    if not arquivo and url:
        progress(0.02, desc="Resolvendo URL…")
        tmpdir = tempfile.TemporaryDirectory()
        arquivo, titulo = baixar_de_url(url.strip(), tmpdir.name, progress)
        base = titulo[:60]

    try:
        progress(0.2, desc="Decodificando áudio…")
        audio = carregar_audio(arquivo)
        duracao = audio.size / 16000

        progress(0.3, desc=f"Carregando modelo em {dispositivo}… (a primeira vez demora)")
        pipe = obter_pipeline(dispositivo)

        config = pipe.get_generation_config()
        config.task = "transcribe"
        config.return_timestamps = True
        codigo = IDIOMAS.get(idioma_nome, "auto")
        if codigo != "auto":
            config.language = f"<|{codigo}|>"

        progress(0.4, desc=f"Transcrevendo {duracao/60:.1f} min de áudio em {dispositivo}…")
        inicio = time.time()
        resultado = _gerar_com_retry(dispositivo, audio, config)
        tempo = time.time() - inicio

        texto = str(resultado).strip()
        carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if base is None:
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
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


def transcrever_imagem(imagem, idioma_nome, progress=gr.Progress()):
    if imagem is None:
        raise gr.Error("Envie ou cole uma imagem primeiro.")

    progress(0.3, desc="Lendo texto da imagem (OCR)…")
    codigo = IDIOMAS_OCR.get(idioma_nome, "por")
    with Image.open(imagem) as img:
        texto = pytesseract.image_to_string(img, lang=codigo).strip()

    if not texto:
        raise gr.Error("Nenhum texto foi encontrado na imagem.")

    carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = Path(imagem).stem[:60]
    arq_txt = SAIDAS / f"{base}_ocr_{carimbo}.txt"
    arq_txt.write_text(texto, encoding="utf-8")

    return texto, str(arq_txt)


def transcrever_pdf(pdf, idioma_nome, progress=gr.Progress()):
    """Extrai o texto de cada página: texto nativo quando existe (grátis, sem
    OCR); OCR a 300dpi só nas páginas que não têm camada de texto (PDF
    escaneado)."""
    if pdf is None:
        raise gr.Error("Envie um arquivo PDF primeiro.")

    codigo = IDIOMAS_OCR.get(idioma_nome, "por")
    partes = []
    with fitz.open(pdf) as doc:
        total = doc.page_count
        for i, pagina in enumerate(doc):
            progress((i + 1) / total, desc=f"Página {i + 1}/{total}")
            texto_pagina = pagina.get_text().strip()
            if not texto_pagina:
                pix = pagina.get_pixmap(dpi=300)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                texto_pagina = pytesseract.image_to_string(img, lang=codigo).strip()
            partes.append(texto_pagina)

    texto = "\n\n".join(partes).strip()
    if not texto:
        raise gr.Error("Nenhum texto foi encontrado no PDF.")

    carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = Path(pdf).stem[:60]
    arq_txt = SAIDAS / f"{base}_{carimbo}.txt"
    arq_txt.write_text(texto, encoding="utf-8")

    return texto, str(arq_txt)


# Ctrl+V "cru" (tecla) só é nativo em componentes de imagem via botão dedicado no Gradio 6;
# este script intercepta o evento de paste do navegador e injeta o arquivo colado no
# <input type=file> visível no momento (áudio/vídeo ou imagem, dependendo da aba aberta).
COLAR_JS = """
<script>
window.addEventListener('paste', (e) => {
    const dt = e.clipboardData;
    if (!dt || !dt.files || dt.files.length === 0) return;
    const entradas = Array.from(document.querySelectorAll('input[type=file]'));
    const alvo = entradas.find((inp) => inp.parentElement && inp.parentElement.offsetParent !== null);
    if (!alvo) return;
    const novo = new DataTransfer();
    for (const arquivo of dt.files) novo.items.add(arquivo);
    alvo.files = novo.files;
    alvo.dispatchEvent(new Event('change', { bubbles: true }));
    e.preventDefault();
});
</script>
"""

with gr.Blocks(title="Transcritor NPU") as app:
    gr.Markdown("# 🎙️ Transcritor NPU\nWhisper large-v3-turbo e OCR rodando localmente no seu Intel Core Ultra.")

    with gr.Tab("Áudio / Vídeo"):
        with gr.Row():
            with gr.Column(scale=1):
                entrada = gr.File(
                    label="Áudio ou vídeo (arquivo, arraste ou Ctrl+V)",
                    file_types=["audio", "video"],
                    type="filepath",
                )
                url = gr.Textbox(label="…ou cole um link (YouTube etc.)", placeholder="https://")
                dispositivo = gr.Dropdown(["NPU", "GPU", "CPU"], value="NPU", label="Dispositivo")
                idioma = gr.Dropdown(list(IDIOMAS), value="Português", label="Idioma")
                botao = gr.Button("Transcrever", variant="primary")
            with gr.Column(scale=2):
                texto = gr.Textbox(label="Transcrição", lines=18, buttons=["copy"])
                downloads = gr.File(label="Baixar (.txt / .srt)", file_count="multiple")
                info = gr.Markdown()
        botao.click(transcrever, [entrada, url, dispositivo, idioma], [texto, downloads, info])

    with gr.Tab("Imagem (OCR)"):
        with gr.Row():
            with gr.Column(scale=1):
                imagem = gr.Image(label="Imagem (arquivo, arraste ou Ctrl+V)", type="filepath")
                idioma_ocr = gr.Dropdown(list(IDIOMAS_OCR), value="Português", label="Idioma do texto")
                botao_ocr = gr.Button("Extrair texto", variant="primary")
            with gr.Column(scale=2):
                texto_ocr = gr.Textbox(label="Texto extraído", lines=18, buttons=["copy"])
                download_ocr = gr.File(label="Baixar (.txt)")
        botao_ocr.click(transcrever_imagem, [imagem, idioma_ocr], [texto_ocr, download_ocr])

    with gr.Tab("PDF → Texto"):
        with gr.Row():
            with gr.Column(scale=1):
                pdf = gr.File(
                    label="PDF (arquivo, arraste ou Ctrl+V)",
                    file_types=[".pdf"],
                    type="filepath",
                )
                idioma_pdf = gr.Dropdown(list(IDIOMAS_OCR), value="Português", label="Idioma (só usado nas páginas escaneadas)")
                botao_pdf = gr.Button("Extrair texto", variant="primary")
            with gr.Column(scale=2):
                texto_pdf = gr.Textbox(label="Texto extraído", lines=18, buttons=["copy"])
                download_pdf = gr.File(label="Baixar (.txt)")
        botao_pdf.click(transcrever_pdf, [pdf, idioma_pdf], [texto_pdf, download_pdf])

if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", inbrowser=True, head=COLAR_JS)
