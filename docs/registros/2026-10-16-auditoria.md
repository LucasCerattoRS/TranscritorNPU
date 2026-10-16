# Auditoria (2026-10-16)

- Base: `main` (1876ee0). Branch: `claude/audit-transcritor-npu-mevqpe`.
- Método: testes com stubs (sem NPU, modelo, ffmpeg ou rede); cada achado tem teste que falhava antes.

## Achados corrigidos (`test/test_auditoria.py`)
1. `app.py:62-70` — pasta `modelo/` ausente ou ilegível estourava erro cru do OpenVINO; agora `gr.Error` com instrução (e o dispositivo falho não entra no cache).
2. `app.py:~158` — título `None` do yt-dlp quebrava com `TypeError` em `titulo[:60]`; agora cai em `audio_url`.
3. `app.py:~248` — imagem corrompida/formato inesperado (OSError) vazava erro cru; agora `gr.Error`.
4. `app.py:~268` — PDF corrompido/protegido vazava erro cru; agora `gr.Error`.

## Verificado, sem defeito reproduzido
- Caminhos com espaço/acento: coberto por `test_nome_com_acento...` (passa).
- Temporários do download: coberto por `test_falha_no_download_limpa...` (passa).
- CI: `pip install pytest numpy`, sem modelo nem dependências pesadas.
- Arquivo de áudio corrompido: ffmpeg com código ≠ 0 já vira `gr.Error`.

## Suposições (não reproduzidas)
- Áudio muito grande: decodificado inteiro para memória (~230 MB/h); não testado com arquivo real.
- Transcrição real, yt-dlp, Tesseract e PDF reais não exercitados.

## Testes
- Antes: 5 falhas, 15 passaram. Depois: 20 passaram (`python3 -m pytest -q test`).
