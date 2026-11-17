# -*- coding: utf-8 -*-
"""Transcritor NPU — Whisper large-v3-turbo via OpenVINO com interface Gradio.

Dispositivos: NPU (Intel AI Boost), GPU (Arc integrada) ou CPU.
Aceita qualquer áudio ou vídeo que o ffmpeg leia (arquivo ou link via yt-dlp)
e imagens (OCR via Tesseract).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

import fitz  # PyMuPDF
import numpy as np
import gradio as gr
import openvino_genai
import pytesseract
import yt_dlp
from PIL import Image

import downloader
import historico

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
_pipeline_lock = Lock()


def obter_pipeline(dispositivo: str) -> openvino_genai.WhisperPipeline:
    with _pipeline_lock:
        if dispositivo not in _pipelines:
            if not MODELO.is_dir():
                raise gr.Error(f"Modelo não encontrado em {MODELO}. Baixe o OpenVINO/whisper-large-v3-turbo-int8-ov e coloque em modelo/ (veja o README).")
            # Se a NPU/GPU não carregar (driver ausente, p.ex. Linux sem intel-npu-driver),
            # cai sozinho para o próximo dispositivo em vez de falhar a transcrição.
            ordem = {"NPU": ["NPU", "GPU", "CPU"], "GPU": ["GPU", "CPU"]}.get(dispositivo, [dispositivo])
            ultimo = None
            for d in ordem:
                try:
                    _pipelines[dispositivo] = openvino_genai.WhisperPipeline(str(MODELO), d, CACHE_DIR=str(CACHE))
                    if d != dispositivo:
                        print(f"[aviso] {dispositivo} indisponível ({str(ultimo).splitlines()[0][:80]}); usando {d}")
                    break
                except Exception as e:
                    ultimo = e
            else:
                raise gr.Error(f"Não consegui carregar o modelo em {dispositivo}: {ultimo}. Confira a pasta modelo/ ou tente outro dispositivo.")
        return _pipelines[dispositivo]


def invalidar_pipeline(dispositivo: str) -> None:
    with _pipeline_lock:
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
    try:
        proc = subprocess.run(cmd, capture_output=True)
    except FileNotFoundError:
        raise gr.Error("ffmpeg não encontrado. Instale o ffmpeg e deixe-o no PATH (veja o README).")
    if proc.returncode != 0:
        raise gr.Error("ffmpeg não conseguiu ler o arquivo: " + proc.stderr.decode(errors="replace")[:500])
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise gr.Error("O arquivo não contém áudio.")
    return audio


def _opcoes_yt_dlp() -> dict:
    """Opções comuns de rede/login do yt-dlp (YouTube + Instagram), usadas por todo download."""
    opcoes = {
        # YouTube exige resolver desafios JS pra liberar os formatos completos;
        # usa o Node.js já instalado na máquina em vez do runtime Deno padrão do yt-dlp.
        "js_runtimes": {"node": {}},
        # yt-dlp novo baixa o solver dos desafios (ejs) do GitHub; sem isso o YouTube devolve 403.
        "remote_components": ["ejs:github"],
    }
    # Instagram (e outros sites logados) exigem sessão autenticada. Ordem de preferência:
    #  1) cookies.txt (formato Netscape) ao lado do app.py — rota mais confiável no
    #     Windows: funciona com o Brave aberto e mesmo com App-Bound Encryption, pois a
    #     exportação acontece dentro do navegador já logado (via extensão "Get cookies.txt").
    #     Está no .gitignore: é uma sessão logada, nunca vai pro git.
    #  2) cookiesfrombrowser("brave") — só funciona com o Brave FECHADO e sem ABE.
    #  3) sem cookies — YouTube e URLs sem login seguem funcionando; conteúdo de IG
    #     que exige sessão vai falhar com "empty media response".
    cookies_txt = PASTA / "cookies.txt"
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
    return opcoes


def baixar_de_url(url: str, pasta_tmp: str, progress: gr.Progress) -> tuple[str, str]:
    """Baixa só a faixa de áudio de uma URL (YouTube etc.) via yt-dlp, sem baixar o vídeo inteiro.
    Usado pelo "Transcrever" quando só há link; descartável depois (pasta temporária)."""

    url = downloader.validar_url(url)
    if not url:
        raise gr.Error("Cole um link HTTP ou HTTPS válido.")

    def avisar(d):
        if d["status"] == "downloading":
            pct = d.get("_percent_str", "").strip()
            progress(0.1, desc=f"Baixando áudio da URL… {pct}")

    opcoes = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(pasta_tmp).as_posix().replace("%", "%%") + "/%(id).64B.%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [avisar],
        **_opcoes_yt_dlp(),
    }

    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = downloader.extrair_um_video(ydl, url)
            caminho = ydl.prepare_filename(info)
    except downloader.DownloadFailed as e:
        raise gr.Error(str(e))
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Não consegui baixar essa URL: {e}")
    return caminho, info.get("title") or "audio_url"


MODOS_DOWNLOAD = ["Vídeo", "Só áudio (MP3)"]
QUALIDADES = ["360p", "720p", "1080p", "Melhor"]
PASTA_DOWNLOADS = SAIDAS / "downloads"


def baixar_midia(url, modo, qualidade, pasta, progress=gr.Progress()):
    """Baixa vídeo (mp4) ou áudio (mp3) para a pasta escolhida e registra no histórico.
    Retorna (caminho do arquivo, título). A mídia fica no disco mesmo se a transcrição
    posterior falhar. Levanta gr.Error com mensagem amigável."""
    limpa = downloader.validar_url(url)
    if not limpa:
        raise gr.Error("Cole um link HTTP ou HTTPS válido.")
    if modo not in MODOS_DOWNLOAD:
        raise gr.Error("Escolha vídeo ou só áudio.")
    audio = modo != "Vídeo"
    pasta = downloader.normalizar_pasta(pasta) if (pasta or "").strip() else str(PASTA_DOWNLOADS)
    registro = {"id": uuid4().hex, "url": limpa, "modo": modo, "qualidade": "" if audio else qualidade,
                "pasta": pasta, "quando": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "status": "downloading", "titulo": "", "arquivo": "", "error": ""}
    _registrar(registro)

    def avisar(d):
        if d.get("status") == "downloading":
            progress(0.1, desc=f"Baixando… {str(d.get('_percent_str', '')).strip()}")

    try:
        progress(0.02, desc="Resolvendo link…")
        titulo, caminho = downloader.run_download(
            limpa, qualidade, audio, False, pasta, avisar, extra_opts=_opcoes_yt_dlp())
        if not caminho or not Path(caminho).is_file():
            raise downloader.DownloadFailed("O download terminou, mas não achei o arquivo final.")
    except downloader.DownloadFailed as e:
        registro.update(status="error", error=str(e))
        _registrar(registro)
        raise gr.Error(str(e))
    registro.update(status="ok", titulo=titulo, arquivo=caminho)
    _registrar(registro)
    return caminho, titulo


_hist_lock = Lock()


def _registrar(registro: dict) -> None:
    """Insere/atualiza o registro (por id) no histórico em disco. Falha de disco não derruba o download."""
    with _hist_lock:
        try:
            caminho = historico.caminho_padrao()
            itens = [i for i in historico.carregar(caminho) if i.get("id") != registro["id"]]
            historico.salvar(caminho, [dict(registro)] + itens)
        except OSError as e:
            print(f"[aviso] não consegui gravar o histórico: {e}")


def tabela_historico():
    with _hist_lock:
        itens = historico.carregar(historico.caminho_padrao())
    return [[i.get("quando", ""), i.get("titulo") or i.get("url", ""), i.get("modo", ""),
             i.get("status", ""), i.get("arquivo") or i.get("error", "")] for i in itens]


def baixar(url, modo, qualidade, pasta, progress=gr.Progress()):
    """Aba Baixar: só baixa."""
    caminho, titulo = baixar_midia(url, modo, qualidade, pasta, progress)
    return f"Salvo: {titulo}\n{caminho}", tabela_historico()


def baixar_e_transcrever(url, modo, qualidade, pasta, dispositivo, idioma, progress=gr.Progress()):
    """Um clique: baixa e transcreve. Se a transcrição falhar, a mídia baixada continua no disco
    e o erro vira aviso (não perde o download)."""
    try:
        caminho, titulo = baixar_midia(url, modo, qualidade, pasta, progress)
    except gr.Error as e:
        return "", None, f"Falha no download: {e}", tabela_historico()
    try:
        texto, arquivos, info = transcrever(caminho, "", dispositivo, idioma, progress)
    except Exception as e:
        msg = getattr(e, "message", None) or str(e)
        return "", None, (f"A transcrição falhou ({msg}), mas a mídia foi salva em: {caminho}. "
                          "Use a aba Áudio / Vídeo para tentar de novo."), tabela_historico()
    return texto, arquivos, f"Mídia salva em: {caminho}\n\n{info}", tabela_historico()


def _ts_srt(segundos: float) -> str:
    # Arredonda pra milissegundos ANTES de quebrar em h/m/s; senão 59.9996 vira "00:00:60,000".
    ms = round(segundos * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _nome_seguro(nome: str) -> str:
    """Título de vídeo vira nome de arquivo: troca o que o Windows proíbe (< > : " / barra invertida | ? * e caracteres de controle)."""
    # Nome de arquivo Linux com byte não UTF-8 chega com surrogateescape (b"\xe9" vira "\udce9") e quebraria o encode abaixo.
    nome = nome.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace").replace("\ufffd", "_")
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome)
    # Reserva espaço para o carimbo, identificador e extensão no limite de 255 bytes.
    return nome.encode("utf-8")[:180].decode("utf-8", errors="ignore").strip(" .") or "transcricao"


def gerar_srt(chunks) -> str:
    blocos = []
    # Trechos sem texto (silêncio) viram legenda vazia; ficam de fora e a numeração segue contínua.
    for i, c in enumerate((c for c in chunks if c.text.strip()), 1):
        blocos.append(f"{i}\n{_ts_srt(c.start_ts)} --> {_ts_srt(c.end_ts)}\n{c.text.strip()}\n")
    return "\n".join(blocos)


def transcrever(arquivo, url, dispositivo, idioma_nome, progress=gr.Progress()):
    if not arquivo and not url:
        raise gr.Error("Envie um arquivo de áudio/vídeo ou cole um link primeiro.")

    tmpdir = None
    base = None
    try:
        if not arquivo and url:
            progress(0.02, desc="Resolvendo URL…")
            tmpdir = tempfile.TemporaryDirectory()
            arquivo, titulo = baixar_de_url(url.strip(), tmpdir.name, progress)
            base = _nome_seguro(titulo[:60])

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
        carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid4().hex
        if base is None:
            base = _nome_seguro(Path(arquivo).stem[:60])

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
    try:
        with Image.open(imagem) as img:
            texto = pytesseract.image_to_string(img, lang=codigo).strip()
    except OSError as e:
        raise gr.Error(f"Não consegui ler a imagem (arquivo corrompido ou formato inesperado): {e}")

    if not texto:
        raise gr.Error("Nenhum texto foi encontrado na imagem.")

    carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid4().hex
    base = _nome_seguro(Path(imagem).stem[:60])
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
    try:
        doc = fitz.open(pdf)
    except Exception as e:
        raise gr.Error(f"Não consegui abrir o PDF (arquivo corrompido ou protegido): {e}")
    with doc:
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

    carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid4().hex
    base = _nome_seguro(Path(pdf).stem[:60])
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

# Cesta de arremesso (estatico/cesta-dropzone.*, projeto próprio do Lukas): zona de upload
# opcional na aba Áudio / Vídeo. O arquivo que cai na cesta é entregue ao MESMO <input type=file>
# do componente "entrada" (id entrada-midia), então o resto do fluxo não muda. Sem os arquivos em
# estatico/, o app abre normalmente sem a cesta.
_ESTATICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estatico")


def montar_head(pasta=_ESTATICO):
    """Devolve o <head> extra: colar (Ctrl+V) e, se os arquivos existirem, a cesta."""
    try:
        with open(os.path.join(pasta, "cesta-dropzone.css"), encoding="utf-8") as f:
            css = f.read()
        with open(os.path.join(pasta, "cesta-dropzone.js"), encoding="utf-8") as f:
            js = f.read()
    except OSError:
        return COLAR_JS
    if "</script" in js.lower() or "</style" in css.lower():
        return COLAR_JS
    return COLAR_JS + "<style>" + css + "</style><script>" + js + "</script>" + CESTA_INIT_JS


CESTA_INIT_JS = """
<script>
(function () {
  function entregar(arquivo) {
    const alvo = document.querySelector('#entrada-midia input[type=file]');
    if (!alvo) return Promise.reject(new Error('campo de arquivo não encontrado'));
    const dt = new DataTransfer();
    dt.items.add(arquivo);
    alvo.files = dt.files;
    alvo.dispatchEvent(new Event('change', { bubbles: true }));
    return Promise.resolve();
  }
  function montar() {
    const raiz = document.getElementById('cesta-midia');
    if (!raiz || raiz.dataset.pronta || !window.CestaDropzone) return;
    raiz.dataset.pronta = '1';
    new window.CestaDropzone(raiz, {
      titulo: 'Arremesse na cesta',
      sub: 'Opcional: solte o áudio ou vídeo aqui e jogue na cesta. Depois clique em Transcrever.',
      aceitar: 'audio/*,video/*', multiplos: false,
      upload: (arquivo, progresso) => entregar(arquivo).then(() => { if (progresso) progresso(1); }),
    });
  }
  new MutationObserver(montar).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('load', montar);
})();
</script>
"""

with gr.Blocks(title="Mídia e transcrição") as app:
    gr.Markdown("# Mídia e transcrição\nBaixe vídeos e transcreva arquivos na mesma tela. Downloads precisam de internet; transcrição e OCR usam os recursos instalados no computador.")

    with gr.Tab("Áudio / Vídeo"):
        with gr.Row():
            with gr.Column(scale=1):
                entrada = gr.File(
                    label="Áudio ou vídeo (arquivo, arraste ou Ctrl+V)",
                    file_types=["audio", "video"],
                    type="filepath",
                    elem_id="entrada-midia",
                )
                with gr.Accordion("Arremessar na cesta (opcional)", open=False):
                    gr.HTML('<div id="cesta-midia"></div>')
                url = gr.Textbox(label="…ou cole um link (só o áudio é usado; para guardar a mídia, use a aba Baixar)", placeholder="https://")
                dispositivo = gr.Dropdown(["NPU", "GPU", "CPU"], value="NPU", label="Dispositivo")
                idioma = gr.Dropdown(list(IDIOMAS), value="Português", label="Idioma")
                botao = gr.Button("Transcrever", variant="primary")
            with gr.Column(scale=2):
                texto = gr.Textbox(label="Transcrição", lines=18, buttons=["copy"])
                downloads = gr.File(label="Baixar (.txt / .srt)", file_count="multiple")
                info = gr.Markdown()
        botao.click(transcrever, [entrada, url, dispositivo, idioma], [texto, downloads, info])

    with gr.Tab("Baixar"):
        gr.Markdown("YouTube, Instagram e outros links. Instagram precisa de `cookies.txt` (exportado do navegador logado) ao lado do `app.py`.")
        with gr.Row():
            with gr.Column(scale=1):
                url_b = gr.Textbox(label="Link", placeholder="https://")
                modo_b = gr.Radio(MODOS_DOWNLOAD, value="Vídeo", label="O que baixar")
                qual_b = gr.Dropdown(QUALIDADES, value="720p", label="Qualidade do vídeo")
                pasta_b = gr.Textbox(label="Pasta de saída", value=str(PASTA_DOWNLOADS))
                disp_b = gr.Dropdown(["NPU", "GPU", "CPU"], value="NPU", label="Dispositivo (para transcrever)")
                idioma_b = gr.Dropdown(list(IDIOMAS), value="Português", label="Idioma (para transcrever)")
                botao_b = gr.Button("Baixar")
                botao_bt = gr.Button("Baixar e transcrever", variant="primary")
            with gr.Column(scale=2):
                info_b = gr.Markdown()
                texto_b = gr.Textbox(label="Transcrição", lines=12, buttons=["copy"])
                downloads_b = gr.File(label="Baixar (.txt / .srt)", file_count="multiple")
                hist_b = gr.Dataframe(
                    headers=["Quando", "Título", "Tipo", "Status", "Arquivo / erro"],
                    value=tabela_historico, label="Histórico de downloads", interactive=False)
        botao_b.click(baixar, [url_b, modo_b, qual_b, pasta_b], [info_b, hist_b])
        botao_bt.click(baixar_e_transcrever, [url_b, modo_b, qual_b, pasta_b, disp_b, idioma_b],
                       [texto_b, downloads_b, info_b, hist_b])

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
    app.launch(server_name="127.0.0.1", inbrowser=True, head=montar_head())
