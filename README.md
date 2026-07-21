# Transcritor NPU

Transcrição de áudio/vídeo local e offline, usando Whisper large-v3-turbo via
[OpenVINO GenAI](https://github.com/openvinotoolkit/openvino.genai), com interface
[Gradio](https://www.gradio.app/). Roda inteiramente na máquina — nada sobe pra nuvem.

Feito para aproveitar a **NPU** (Neural Processing Unit) de notebooks Intel Core Ultra
(Meteor Lake em diante), mas também roda em GPU integrada ou CPU.

## Por quê

Transcrever áudio/vídeo geralmente significa mandar o arquivo pra um serviço de nuvem.
Este projeto faz o mesmo localmente, usando um acelerador de IA que a maioria dos
notebooks Intel recentes já tem e não usa pra nada.

## Requisitos

- Windows com driver de NPU Intel atualizado (Intel AI Boost) — a NPU só é reconhecida
  com driver recente o suficiente para o seu SO.
- Python 3.13 (OpenVINO GenAI ainda não suporta 3.14).
- [ffmpeg](https://ffmpeg.org/) no PATH (decodifica qualquer áudio/vídeo).
- O modelo `OpenVINO/whisper-large-v3-turbo-int8-ov` (~1,7 GB), baixado à parte —
  não vai no repositório por tamanho. Coloque em `modelo/`.

## Uso

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt   # gradio, openvino-genai, numpy
python app.py
```

Ou, no Windows, duplo clique em `Iniciar Transcritor.bat`. O navegador abre sozinho.

Escolha o dispositivo (NPU/GPU/CPU), o idioma, envie um áudio ou vídeo e clique em
Transcrever. Gera `.txt` e `.srt` (com timestamps) em `saidas/`.

## Notas de performance

Na NPU, a primeira transcrição depois de trocar de dispositivo recompila um cache
(pode levar minutos); as seguintes, com cache quente, ficam bem mais rápidas que
tempo real. GPU integrada costuma ser a mais rápida de largada (sem esse aquecimento);
CPU é a mais lenta, mas sempre disponível.

## Licença

CC BY-NC-SA 4.0 — uso e adaptação livres para fins não comerciais, com atribuição.
