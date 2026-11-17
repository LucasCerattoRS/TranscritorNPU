"""Wrapper do yt-dlp (cópia adaptada de ~/Projetos/video-downloader/downloader.py:
repo irmão, copiado em vez de importado para o Transcritor continuar portátil).
Adaptações: qualidade 360p, `extra_opts` (cookies/JS do YouTube) e retorno com o
caminho final do arquivo.

Wrapper do yt-dlp: detecta plataforma, monta opções e roda o download.

Usado como biblioteca pelo worker do app.py. A função `run_download` é
bloqueante (roda dentro de um executor de thread) e chama `on_progress`
a cada atualização vinda dos progress_hooks do yt-dlp.
"""

from __future__ import annotations

import os
import shutil
from urllib.parse import urlparse

# yt_dlp é importado de forma preguiçosa dentro de run_download: é uma
# dependência pesada e só necessária no download real. Assim o módulo (e as
# funções puras detect_platform/preset_folder/_friendly_error/build_options)
# importa e é testável mesmo sem yt-dlp instalado.


# Presets de pasta relativos a ~/Downloads/Videos
def _downloads_base() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads", "Videos")


FOLDER_PRESETS = {
    "youtube": os.path.join(_downloads_base(), "YouTube"),
    "instagram": os.path.join(_downloads_base(), "Instagram"),
    "other": _downloads_base(),
}


def detect_platform(url: str) -> str:
    """Retorna 'youtube', 'instagram' ou 'other' a partir do domínio."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return "other"
    if host.startswith("www."):
        host = host[4:]
    if host in ("youtube.com", "youtu.be", "m.youtube.com") or host.endswith(".youtube.com"):
        return "youtube"
    if host in ("instagram.com", "instagr.am") or host.endswith(".instagram.com"):
        return "instagram"
    return "other"


def validar_url(url: str) -> str | None:
    """Retorna a URL limpa se for http(s) com host e sem espaços internos; senão None."""
    url = (url or "").strip()
    if not url or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return None
    try:
        url.encode("utf-8")
        p = urlparse(url)
        host = p.hostname
    except ValueError:
        return None
    if p.scheme.lower() not in ("http", "https") or not host:
        return None
    return url


def normalizar_pasta(folder: str) -> str:
    """Expande ~ e torna absoluto (pasta relativa dependeria de onde o servidor foi iniciado)."""
    return os.path.abspath(os.path.expanduser(folder.strip()))


# --- Limite de comprimento de caminho (Windows: MAX_PATH = 260) ------------
# pasta + separador + nome do arquivo precisa ficar abaixo de LIMITE_CAMINHO.
# O nome do vídeo é "<título> [<id>].<ext>", e durante o download o yt-dlp
# grava variações maiores: "<…>.f137.mp4.part", "<…>.temp.mp4", "<…>.pt-BR.vtt".
LIMITE_CAMINHO = 250
ID_MAX = 24            # bytes do id no nome (YouTube usa 11; Instagram ~19)
RESERVA_SUFIXOS = 30   # extensão + ".fNNN" + ".part"/".temp"/".ytdl" + idioma da legenda
TITULO_MIN = 16        # abaixo disso o nome perde o sentido: pede pasta mais curta
TITULO_MAX = 200       # teto antigo (%(title).200B), mantido para pastas curtas
NOME_FOTO_MAX = 64     # gallery-dl/Instagram: "<media_id>.<ext>" (~40) + ".part"
_FIXO_VIDEO = len(" [") + ID_MAX + len("]") + RESERVA_SUFIXOS


class CaminhoLongo(ValueError):
    """Pasta de destino longa demais para caber um nome de arquivo."""


def _comprimento(folder: str) -> int:
    """Comprimento como o Windows conta (unidades UTF-16): emoji vale 2."""
    return len(folder.encode("utf-16-le")) // 2


def _msg_caminho_longo(folder: str) -> str:
    return (
        f"O caminho da pasta de destino é longo demais ({_comprimento(folder)} caracteres): "
        "não sobra espaço para o nome do arquivo dentro do limite de "
        f"{LIMITE_CAMINHO} caracteres do Windows. Escolha uma pasta com caminho mais "
        "curto (ex.: C:\\Videos)."
    )


def bytes_titulo(folder: str) -> int:
    """Quantos bytes do título cabem no nome do vídeo para essa pasta.

    O yt-dlp corta o título em bytes (UTF-8); como cada caractere ocupa ao
    menos 1 byte (e ao menos tantos bytes quanto unidades UTF-16 no Windows),
    o corte em bytes nunca deixa o caminho maior que o calculado.
    Levanta CaminhoLongo se não sobrar ao menos TITULO_MIN.
    """
    # caminho final <= LIMITE_CAMINHO - 1 (estritamente abaixo do limite)
    disponivel = LIMITE_CAMINHO - 1 - _comprimento(folder) - len(os.sep) - _FIXO_VIDEO
    if disponivel < TITULO_MIN:
        raise CaminhoLongo(_msg_caminho_longo(folder))
    return min(TITULO_MAX, disponivel)


def verificar_pasta_fotos(folder: str) -> None:
    """Levanta CaminhoLongo se a pasta não comporta o nome das fotos."""
    if _comprimento(folder) + len(os.sep) + NOME_FOTO_MAX >= LIMITE_CAMINHO:
        raise CaminhoLongo(_msg_caminho_longo(folder))


def verificar_comprimento_pasta(folder: str) -> str | None:
    """Checagem antes de enfileirar (vídeo ou foto): mensagem de erro ou None."""
    try:
        bytes_titulo(folder)
        verificar_pasta_fotos(folder)
    except CaminhoLongo as exc:
        return str(exc)
    return None


def preset_folder(platform: str) -> str:
    return FOLDER_PRESETS.get(platform, FOLDER_PRESETS["other"])


# Mapa de qualidade -> format string do yt-dlp
_QUALITY_FORMATS = {
    "360p": "bv*[height<=360]+ba/b[height<=360]/b",
    "best": "bv*+ba/b",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]/b",
    "720p": "bv*[height<=720]+ba/b[height<=720]/b",
}


MSG_SEM_FFMPEG = (
    "ffmpeg não encontrado: ele é necessário para juntar vídeo+áudio, converter "
    "para MP3 e embutir legendas. Instale (Windows: winget install Gyan.FFmpeg; "
    "Fedora: sudo dnf install ffmpeg) e reinicie o programa."
)
MSG_DISCO_CHEIO = (
    "Sem espaço em disco na pasta de destino. Libere espaço e tente de novo "
    "(o arquivo parcial .part fica na pasta; ao baixar de novo, continua de onde parou)."
)


def _sem_espaco(m: str) -> bool:
    """`m` já em minúsculas. Errno 28 (ENOSPC) no Linux/macOS e no Windows."""
    return "errno 28" in m or "no space left" in m or "not enough space on the disk" in m


def _friendly_error(message: str) -> str:
    """Traduz mensagens comuns do yt-dlp para algo curto e legível."""
    m = message.lower()
    if _sem_espaco(m):
        return MSG_DISCO_CHEIO
    if "ffmpeg" in m and ("not installed" in m or "not found" in m):
        return MSG_SEM_FFMPEG
    if "unsupported url" in m or "no video" in m or "unable to extract" in m:
        return "Link não reconhecido ou sem vídeo."
    if ("private" in m or "login required" in m or "not available" in m
            or "unavailable" in m or "removed" in m or "does not exist" in m):
        return "Vídeo privado, removido ou indisponível."
    if "429" in m or "too many requests" in m or "rate-limit" in m or "rate limit" in m:
        return "O site pediu pra desacelerar (limite de requisições). Tente de novo em alguns minutos."
    if "urlopen" in m or "getaddrinfo" in m or "timed out" in m or "connection" in m:
        return "Falha de conexão."
    # Fallback: primeira linha, sem prefixo "ERROR:"
    first = message.strip().splitlines()[0] if message.strip() else "Erro desconhecido."
    return first.replace("ERROR:", "").strip() or "Erro desconhecido."


class DownloadFailed(Exception):
    """Erro de download já traduzido para exibição."""


class NoVideoContent(DownloadFailed):
    """O post não tem vídeo (provavelmente é foto/carrossel) — sinaliza o
    worker do app.py a tentar o fallback via photo_downloader."""


def build_options(quality: str, audio_only: bool, subtitles: bool, folder: str, progress_hook) -> dict:
    # % na pasta (ex.: "100% pronto") seria lido como campo do template do yt-dlp
    # Título cortado conforme o comprimento da pasta (limite de caminho do Windows)
    n = bytes_titulo(folder)
    outtmpl = os.path.join(
        folder.replace("%", "%%"), f"%(title).{n}B [%(id).{ID_MAX}B].%(ext)s"
    )
    opts: dict = {
        "outtmpl": outtmpl,
        "progress_hooks": [progress_hook],
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": False,
        "windowsfilenames": True,
        "ignoreerrors": False,
    }

    if audio_only:
        opts["format"] = "ba/b"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        opts["format"] = _QUALITY_FORMATS.get(quality, _QUALITY_FORMATS["best"])
        opts["merge_output_format"] = "mp4"
        if subtitles:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = ["pt", "pt-BR", "pt-orig", "en"]
            opts["postprocessors"] = [{"key": "FFmpegEmbedSubtitle"}]

    return opts


def extrair_um_video(ydl, url):
    """Resolve o link SEM baixar e recusa playlist antes de qualquer download.

    `noplaylist` não impede links explícitos de playlist: com download=True o
    yt-dlp baixaria todos os itens e só o primeiro seria usado.
    """
    info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict) or info.get("entries") is not None or info.get("_type") == "playlist":
        raise DownloadFailed("Use o link de um único vídeo (playlists não são aceitas).")
    if hasattr(ydl, "process_ie_result"):
        return ydl.process_ie_result(info, download=True)
    return ydl.extract_info(url, download=True)


def run_download(
    url: str,
    quality: str,
    audio_only: bool,
    subtitles: bool,
    folder: str,
    progress_hook,
    extra_opts: dict | None = None,
) -> tuple[str, str | None]:
    """Roda o download (bloqueante). Retorna (título, caminho do arquivo final ou None).

    Levanta DownloadFailed com mensagem amigável em caso de erro.
    """
    try:
        import yt_dlp  # dependência pesada — importada só no download real
    except ImportError as exc:
        raise DownloadFailed(
            "yt-dlp não está instalado. Rode: pip install -r requirements.txt"
        ) from exc

    # MP3 e legenda embutida só acontecem no pós-processamento: sem ffmpeg o
    # yt-dlp baixaria tudo para só então falhar (deixando o arquivo e uma
    # mensagem em inglês com flag de linha de comando). Avisa antes.
    if (audio_only or subtitles) and shutil.which("ffmpeg") is None:
        raise DownloadFailed(MSG_SEM_FFMPEG)

    try:
        opts = build_options(quality, audio_only, subtitles, folder, progress_hook)
    except CaminhoLongo as exc:
        raise DownloadFailed(str(exc)) from exc
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as exc:
        raise DownloadFailed(f"Não consegui usar a pasta de destino: {exc.strerror or exc}") from exc
    opts.update(extra_opts or {})

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = extrair_um_video(ydl, url)
    except yt_dlp.utils.DownloadError as exc:
        m = str(exc).lower()
        no_video = "no video formats found" in m or "there is no video in this post" in m
        if no_video and detect_platform(url) == "instagram":
            raise NoVideoContent(_friendly_error(str(exc))) from exc
        raise DownloadFailed(_friendly_error(str(exc))) from exc
    except DownloadFailed:
        raise
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira erro amigável
        raise DownloadFailed(_friendly_error(str(exc))) from exc

    # Playlists desativadas, mas extract_info pode retornar entries em alguns casos
    if info is not None and "entries" in info:
        info = next((entry for entry in (info["entries"] or ()) if entry is not None), None)
    if info is None:
        raise DownloadFailed("Não foi possível obter o vídeo.")

    # Depois dos pós-processadores (merge, MP3) o filepath final fica em requested_downloads.
    caminho = None
    for r in info.get("requested_downloads") or ():
        caminho = r.get("filepath") or caminho
    return info.get("title") or "vídeo", caminho
