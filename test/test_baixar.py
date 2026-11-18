"""Testes da aba Baixar (download + histórico + baixar e transcrever): yt-dlp falso, sem rede."""

import sys
import types

import pytest

import app
import downloader
import historico


class _FalhaDownload(Exception):
    pass


def _yt_dlp_falso(tmp_arquivo=None, erro=None, capturado=None):
    """Módulo yt_dlp falso. Cria `tmp_arquivo` (o 'arquivo final') ao baixar."""
    class YoutubeDL:
        def __init__(self, opts):
            if capturado is not None:
                capturado.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            if erro:
                raise erro
            tmp_arquivo.write_bytes(b"x")
            return {"title": "Meu vídeo", "requested_downloads": [{"filepath": str(tmp_arquivo)}]}

    mod = types.ModuleType("yt_dlp")
    mod.YoutubeDL = YoutubeDL
    mod.utils = types.SimpleNamespace(DownloadError=_FalhaDownload)
    return mod


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRITOR_HISTORICO", str(tmp_path / "hist" / "h.json"))
    monkeypatch.setattr(app, "_opcoes_yt_dlp", lambda: {"cookiefile": "cookies-falso.txt"})
    monkeypatch.setattr(downloader.shutil, "which", lambda nome: "/usr/bin/ffmpeg")
    return tmp_path


def test_baixar_video_720_usa_formato_extra_opts_e_grava_historico(ambiente, monkeypatch):
    alvo = ambiente / "saida" / "Meu vídeo [abc].mp4"
    alvo.parent.mkdir()
    opts = {}
    monkeypatch.setitem(sys.modules, "yt_dlp", _yt_dlp_falso(alvo, capturado=opts))

    caminho, titulo = app.baixar_midia("https://youtu.be/abc", "Vídeo", "720p", str(alvo.parent))

    assert (caminho, titulo) == (str(alvo), "Meu vídeo")
    assert "height<=720" in opts["format"]
    assert opts["cookiefile"] == "cookies-falso.txt"  # extra_opts chegaram ao yt-dlp
    itens = historico.carregar(historico.caminho_padrao())
    assert len(itens) == 1 and itens[0]["status"] == "ok" and itens[0]["arquivo"] == str(alvo)
    assert app.tabela_historico()[0][3] == "ok"


def test_baixar_audio_pede_mp3(ambiente, monkeypatch):
    alvo = ambiente / "Meu vídeo [abc].mp3"
    opts = {}
    monkeypatch.setitem(sys.modules, "yt_dlp", _yt_dlp_falso(alvo, capturado=opts))
    app.baixar_midia("https://youtu.be/abc", "Só áudio (MP3)", "720p", str(ambiente))
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"
    assert opts["format"] == "ba/b"


@pytest.mark.parametrize("url", ["", "ftp://x/y", "https://", "https://a b", "javascript:alert(1)"])
def test_url_invalida_nao_chama_yt_dlp_nem_grava_historico(ambiente, url):
    with pytest.raises(app.gr.Error, match="link"):
        app.baixar_midia(url, "Vídeo", "720p", str(ambiente))
    assert historico.carregar(historico.caminho_padrao()) == []


def test_falha_de_download_vira_erro_amigavel_e_historico_de_erro(ambiente, monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", _yt_dlp_falso(erro=_FalhaDownload("ERROR: Private video")))
    with pytest.raises(app.gr.Error, match="privado"):
        app.baixar_midia("https://www.instagram.com/p/x", "Vídeo", "720p", str(ambiente))
    item = historico.carregar(historico.caminho_padrao())[0]
    assert item["status"] == "error" and "privado" in item["error"]


def test_baixar_e_transcrever_ok(ambiente, monkeypatch):
    alvo = ambiente / "v.mp4"
    monkeypatch.setitem(sys.modules, "yt_dlp", _yt_dlp_falso(alvo))
    chamado = {}

    def falso(arquivo, url, disp, idioma, progress=None):
        chamado.update(arquivo=arquivo, url=url, disp=disp)
        return "texto", ["a.txt"], "info"

    monkeypatch.setattr(app, "transcrever", falso)
    texto, arquivos, info, _ = app.baixar_e_transcrever(
        "https://youtu.be/abc", "Vídeo", "360p", str(ambiente), "NPU", "Português")
    assert texto == "texto" and arquivos == ["a.txt"] and str(alvo) in info
    assert chamado == {"arquivo": str(alvo), "url": "", "disp": "NPU"}


def test_transcricao_falha_mas_midia_continua_no_disco(ambiente, monkeypatch):
    alvo = ambiente / "v.mp4"
    monkeypatch.setitem(sys.modules, "yt_dlp", _yt_dlp_falso(alvo))

    def quebra(*a, **k):
        raise app.gr.Error("modelo não encontrado")

    monkeypatch.setattr(app, "transcrever", quebra)
    texto, arquivos, info, tabela = app.baixar_e_transcrever(
        "https://youtu.be/abc", "Vídeo", "720p", str(ambiente), "CPU", "Português")
    assert texto == "" and arquivos is None
    assert alvo.exists() and str(alvo) in info and "modelo não encontrado" in info
    assert tabela[0][3] == "ok"  # o download segue registrado como concluído


def test_baixar_e_transcrever_download_falho_nao_levanta(ambiente, monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", _yt_dlp_falso(erro=_FalhaDownload("429 Too Many Requests")))
    texto, arquivos, info, _ = app.baixar_e_transcrever(
        "https://youtu.be/abc", "Vídeo", "720p", str(ambiente), "CPU", "Português")
    assert texto == "" and "Falha no download" in info


def test_historico_marca_interrompidos_e_ignora_arquivo_corrompido(tmp_path):
    arq = tmp_path / "h.json"
    historico.salvar(str(arq), [{"id": "1", "status": "downloading"}, {"id": "2", "status": "ok"}])
    itens = historico.carregar(str(arq))
    assert [i["status"] for i in itens] == ["error", "ok"]
    historico.salvar(str(arq), [{"id": ["lista"], "status": "downloading"}, {"id": "2", "status": "downloading"}])
    assert [i["status"] for i in historico.carregar(str(arq), {"2"})] == ["error", "downloading"]
    arq.write_text("{não é json", encoding="utf-8")
    assert historico.carregar(str(arq)) == []


def test_downloader_plataforma_e_validacao():
    assert downloader.detect_platform("https://www.instagram.com/reel/x") == "instagram"
    assert downloader.detect_platform("https://youtu.be/x") == "youtube"
    assert downloader.validar_url("  https://a.com/x  ") == "https://a.com/x"
    assert downloader.validar_url("https://a.com/x y") is None


def test_pasta_com_porcento_nao_vira_campo_do_template(tmp_path):
    opts = downloader.build_options("720p", False, False, str(tmp_path / "100% pronto"), lambda d: None)
    assert "100%% pronto" in opts["outtmpl"]


def test_playlist_e_recusada_antes_de_baixar():
    chamadas = []

    class YDL:
        def extract_info(self, url, download=True):
            chamadas.append(download)
            return {"_type": "playlist", "entries": [{"title": "a"}, {"title": "b"}]}

    with pytest.raises(downloader.DownloadFailed, match="único vídeo"):
        downloader.extrair_um_video(YDL(), "https://youtube.com/playlist?list=x")
    assert chamadas == [False]  # nada foi baixado


def test_video_unico_resolve_sem_baixar_e_depois_processa():
    passos = []

    class YDL:
        def extract_info(self, url, download=True):
            passos.append(("extract", download))
            return {"title": "v", "id": "1"}

        def process_ie_result(self, info, download=True):
            passos.append(("process", download))
            return {**info, "requested_downloads": []}

    info = downloader.extrair_um_video(YDL(), "https://youtu.be/1")
    assert info["title"] == "v" and passos == [("extract", False), ("process", True)]


def test_pasta_sem_permissao_vira_download_failed(ambiente, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "yt_dlp", _yt_dlp_falso(tmp_path / "x.mp4"))

    def nega(*a, **k):
        raise PermissionError(13, "Permissão negada")

    monkeypatch.setattr(downloader.os, "makedirs", nega)
    with pytest.raises(downloader.DownloadFailed, match="pasta de destino"):
        downloader.run_download("https://youtu.be/abc", "720p", False, False, str(tmp_path / "sem"), lambda d: None)


def test_historico_nao_interrompe_download_em_andamento_neste_processo(ambiente, monkeypatch):
    """Recarregar a página ou começar outro download no meio de um download não pode
    marcar o primeiro como "Interrompido: o servidor foi reiniciado"."""
    vistos = {}
    alvo_b = ambiente / "b.mp4"
    yt_b = _yt_dlp_falso(alvo_b)

    class YoutubeDL(_yt_dlp_falso(ambiente / "a.mp4").YoutubeDL):
        def extract_info(self, url, download=True):
            if download:  # 1ª chamada (download=False) resolve o link: é aí que o cenário roda
                return super().extract_info(url, download)
            vistos["tabela"] = app.tabela_historico()  # página recarregada no meio do download
            monkeypatch.setitem(sys.modules, "yt_dlp", yt_b)
            app.baixar_midia("https://youtu.be/b", "Vídeo", "720p", str(ambiente))  # 2º download
            monkeypatch.setitem(sys.modules, "yt_dlp", yt_a)
            vistos["depois_do_b"] = historico.carregar(historico.caminho_padrao())
            return super().extract_info(url, download)

    yt_a = types.ModuleType("yt_dlp")
    yt_a.YoutubeDL = YoutubeDL
    yt_a.utils = types.SimpleNamespace(DownloadError=_FalhaDownload)
    monkeypatch.setitem(sys.modules, "yt_dlp", yt_a)

    app.baixar_midia("https://youtu.be/a", "Vídeo", "720p", str(ambiente))

    assert [linha[3] for linha in vistos["tabela"]] == ["downloading"]
    # lido "de fora" (como num reinício): o B está ok e o A ficou gravado como baixando, não como erro
    assert [(i["url"][-1], i["status"]) for i in vistos["depois_do_b"]] == [("b", "ok"), ("a", "error")]
    assert vistos["depois_do_b"][1]["error"].startswith("Interrompido")
    final = historico.carregar(historico.caminho_padrao())
    assert [(i["url"][-1], i["status"]) for i in final] == [("a", "ok"), ("b", "ok")]
    assert app._ativos == set()


def test_erro_inesperado_no_download_nao_deixa_item_baixando(ambiente, monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", _yt_dlp_falso(erro=_FalhaDownload("x")))
    monkeypatch.setattr(app, "_opcoes_yt_dlp", lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        app.baixar_midia("https://youtu.be/abc", "Vídeo", "720p", str(ambiente))
    item = historico.carregar(historico.caminho_padrao())[0]
    assert item["status"] == "error" and "inesperado" in item["error"]
    assert app._ativos == set()
