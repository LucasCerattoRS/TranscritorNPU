# Roteiro de estudo — Transcritor NPU

> Transcrição de áudio/vídeo **local e offline** com Whisper large-v3-turbo via
> OpenVINO GenAI + interface Gradio. O interesse de estudo aqui é **inferência
> local num acelerador de IA (a NPU) que a maioria dos notebooks Intel tem e não
> usa**, e como envolver isso numa UI web sem servidor de nuvem.
> Se você só tem 20 minutos: leia `app.py` (a montagem da UI) e `experimentos-openvino/hello_openvino.py`.

## Antes de começar — prove que roda

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux: ver LINUX.md)
pip install -r requirements.txt   # gradio, openvino-genai, numpy, pytesseract, yt-dlp, Pillow, pymupdf
python -m pytest test/ -q         # test/test_srt.py — formatação de legenda, sem modelo nem NPU
python app.py                     # abre o navegador na UI Gradio
```

O modelo (`whisper-large-v3-turbo-int8-ov`, ~1,7 GB) **não vai no repo** — baixa
à parte pra `modelo/`. Sem ele, a UI abre mas a transcrição falha. O `pytest`
não precisa do modelo.

## O que este projeto ensina

- **NPU / OpenVINO GenAI** — o Whisper roda num runtime da Intel que sabe usar a
  NPU (Meteor Lake+), a GPU integrada ou a CPU. O usuário escolhe o dispositivo
  na UI. `experimentos-openvino/hello_openvino.py` é o "olá mundo" disso.
- **Gradio** — construir uma UI web (abas, upload, colar com Ctrl+V, colar link)
  em Python puro, sem HTML/JS. `app.py` é quase todo `gr.Blocks(...)`.
- **Pipeline de mídia** — `ffmpeg` decodifica qualquer formato; `yt-dlp` resolve
  um link do YouTube; `pytesseract` faz OCR de imagem; `pymupdf` extrai texto de
  PDF (nativo ou escaneado). Um app, várias entradas, uma saída (`.txt`/`.srt`).
- **Formato SRT** — `test/test_srt.py` testa a geração de legenda com timestamps
  (`HH:MM:SS,mmm`). É a única parte 100% pura/testável.

## Ordem de leitura

1. **`README.md`** — requisitos (driver de NPU, Python 3.13, ffmpeg, Tesseract, modelo) e o "por quê".
2. **`experimentos-openvino/hello_openvino.py`** — a forma mínima de carregar um modelo OpenVINO e rodar inferência. Depois `chat_openvino.py` e `server.py` (variações).
3. **`app.py`** — a UI de verdade. Leia procurando: a definição das abas (Áudio/Vídeo, Imagem/OCR, PDF), o seletor de dispositivo, e onde cada aba chama o pipeline.
4. **`test/test_srt.py`** — a geração de `.srt`. Rode, quebre a formatação de propósito, veja falhar.
5. **`LINUX.md`** — o que muda pra rodar no Fedora.

## Exercícios

**A.** Rode `pytest test/ -q`. Quantos testes? O que cada um verifica na string de legenda?
✅ *pronto quando* você sabe dizer o que acontece se um timestamp passar de 1 hora.

**B.** Abra `app.py` e ache onde a lista de idiomas é definida. Adicione um idioma novo.
✅ *pronto quando* ele aparece no dropdown da UI.

**C.** (precisa do modelo baixado) Transcreva o `teste.wav` do repo nos 3 dispositivos
(NPU, GPU, CPU) e cronometre.
✅ *pronto quando* você tem os 3 tempos — é o ponto do projeto.
