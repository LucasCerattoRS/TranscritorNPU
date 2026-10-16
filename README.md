# Transcritor NPU

Transcrição de áudio/vídeo local e offline, usando Whisper large-v3-turbo via
[OpenVINO GenAI](https://github.com/openvinotoolkit/openvino.genai), com interface
[Gradio](https://www.gradio.app/). Roda inteiramente na máquina — nada sobe pra nuvem.

Feito para aproveitar a **NPU** (Neural Processing Unit) de notebooks Intel Core Ultra
(Meteor Lake em diante), mas também roda em GPU integrada ou CPU.

Além de áudio/vídeo, também extrai texto de **imagens (OCR)** e de **PDFs**
(nativo ou escaneado), e aceita **links** (YouTube etc.) diretamente, sem
precisar baixar o arquivo manualmente antes.

## Estado

Em uso pessoal no Windows (Core Ultra 5 125H). Port pro Linux adaptado mas **não
validado** no Fedora (ver `LINUX.md`). Testes automáticos (stubs) cobrem legenda, nomes de arquivo, o fluxo
de transcrição, limpeza de temporários e erros do ffmpeg — transcrição real exige o modelo e o hardware.

## Por quê

Transcrever áudio/vídeo geralmente significa mandar o arquivo pra um serviço de nuvem.
Este projeto faz o mesmo localmente, usando um acelerador de IA que a maioria dos
notebooks Intel recentes já tem e não usa pra nada.

## Requisitos

- Windows com driver de NPU Intel atualizado (Intel AI Boost) — a NPU só é reconhecida
  com driver recente o suficiente para o seu SO.
- Python 3.13 (OpenVINO GenAI ainda não suporta 3.14).
- [ffmpeg](https://ffmpeg.org/) no PATH (decodifica qualquer áudio/vídeo).
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) instalado (ex.: `winget install UB-Mannheim.TesseractOCR`),
  com o pacote de idioma `por` baixado em `tessdata/` — usado pela aba de OCR de imagem.
- Node.js instalado — usado pelo `yt-dlp` para resolver os desafios JS do YouTube ao
  baixar áudio de um link.
- O modelo `OpenVINO/whisper-large-v3-turbo-int8-ov` (~1,7 GB), baixado à parte —
  não vai no repositório por tamanho. Coloque em `modelo/`.

## Uso

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt   # gradio, openvino-genai, numpy, pytesseract, yt-dlp, Pillow, pymupdf
python app.py
```

Ou duplo clique em `Iniciar Transcritor.bat`. O navegador abre sozinho.

Linux (Fedora):

```bash
sudo dnf install ffmpeg tesseract tesseract-langpack-por
python -m venv .venv && .venv/bin/pip install -r requirements.txt
./iniciar.sh
```

### Rodar os testes em máquina sem NPU

Os testes não precisam de NPU, modelo, ffmpeg, rede nem das dependências pesadas
(gradio, openvino, etc.): `test/conftest.py` as substitui por stubs. Basta:

```bash
pip install pytest numpy
python -m pytest -q test
```

### Rodar o app em máquina sem NPU

Instale as dependências normalmente, coloque o modelo em `modelo/` e escolha **CPU**
(ou **GPU**) no menu "Dispositivo" da interface. A NPU é opcional; só fica mais lenta
na primeira execução de cada dispositivo (compilação de cache). Sem o modelo, o app
sobe, mas não transcreve.

Na aba **Áudio / Vídeo**: escolha o dispositivo (NPU/GPU/CPU) e o idioma, envie um
arquivo, arraste, cole com Ctrl+V ou cole um link — e clique em Transcrever. Gera
`.txt` e `.srt` (com timestamps) em `saidas/`.

Na aba **Imagem (OCR)**: envie, arraste ou cole (Ctrl+V) uma imagem e clique em
Extrair texto. Gera `.txt` em `saidas/`.

Na aba **PDF → Texto**: envie um PDF e clique em Extrair texto. Cada página tenta
extrair o texto nativo primeiro (grátis, instantâneo); páginas sem camada de texto
(PDF escaneado) caem automaticamente para OCR a 300dpi. Gera `.txt` em `saidas/`.

Ctrl+V funciona nas abas de áudio/vídeo e imagem: um script injetado na página
intercepta o evento de colar do navegador e entrega o arquivo pro componente ativo
(ver `COLAR_JS` em `app.py`) — não é um recurso nativo do Gradio para upload de
arquivo genérico.

## Notas de performance

Na NPU, a primeira transcrição depois de trocar de dispositivo recompila um cache
(pode levar minutos); as seguintes, com cache quente, ficam bem mais rápidas que
tempo real. GPU integrada costuma ser a mais rápida de largada (sem esse aquecimento);
CPU é a mais lenta, mas sempre disponível.

## Estrutura

| Caminho | O que é |
|---|---|
| `app.py` | O app inteiro: decodificação (ffmpeg), download (yt-dlp), Whisper (OpenVINO), OCR (Tesseract), PDF (PyMuPDF) e a UI Gradio. |
| `test/test_srt.py` | Testes das funções puras (`_ts_srt`, `gerar_srt`, `_nome_seguro`). |
| `test/test_fluxo_transcricao.py` | Fluxo de `transcrever` com pipeline/ffmpeg falsos: nomes com acento, limpeza de temporários, erro do ffmpeg, SRT sem trechos vazios. |
| `test/conftest.py` | Stubs das dependências pesadas para os testes. |
| `Iniciar Transcritor.bat` / `iniciar.sh` | Atalhos de inicialização (Windows / Linux). |
| `LINUX.md` | Roteiro do port pro Fedora (driver `intel_vpu`, dependências). |
| `experimentos-openvino/` | Scripts soltos de estudo (ResNet, Phi-3 por CLI e por HTTP). Não fazem parte do app. |
| `docs/estudo/ROTEIRO.md` | Roteiro de estudo do projeto. |
| `modelo/`, `cache/`, `saidas/` | Criados localmente; fora do git. |

## Tecnologias

Python 3.13 · OpenVINO GenAI (`WhisperPipeline`) · Gradio 6 · ffmpeg · yt-dlp ·
Tesseract (pytesseract) · PyMuPDF · NumPy · pytest.

## Pendências

- Validar o port no Fedora (NPU via `intel_vpu`).
- Download de Instagram depende de `cookies.txt` ou do Brave fechado; sem isso falha.
- Não há botão de cancelar: uma transcrição em andamento não é interrompida (o ffmpeg e o `generate` são chamadas bloqueantes).
- Arquivos muito longos são decodificados inteiros para a memória (PCM float32 16 kHz ≈ 230 MB por hora de áudio).
- Transcrição real (modelo + NPU) nunca é exercitada pelos testes.

## Para estudar

1. **Cache de recurso caro + retry por invalidação** — `app.py` (`obter_pipeline`, `_gerar_com_retry`): um
   `WhisperPipeline` por dispositivo fica num dicionário; se a NPU devolve
   `DEVICE_LOST`, o pipeline é descartado e recriado uma vez.
2. **ffmpeg como decodificador universal via pipe** — `app.py` (`carregar_audio`): saída
   `f32le` mono 16 kHz em stdout, lida direto com `np.frombuffer` sem arquivo temporário.
3. **Aritmética de tempo em inteiros** — `app.py` (`_ts_srt`): arredondar pra
   milissegundos antes de `divmod` evita o bug clássico de "60 segundos" no SRT.
4. **Limpeza garantida com `try/finally`** — `transcrever`: a pasta temporária do
   download é criada dentro do `try`, então some mesmo quando o download falha.
5. **Testar sem hardware com stubs** — `test/conftest.py` e
   `test/test_fluxo_transcricao.py`: troca de dependências em `sys.modules` e
   `monkeypatch` para exercitar o fluxo real sem NPU nem modelo.
6. **Fallback texto nativo → OCR por página** — `app.py` (`transcrever_pdf`): PyMuPDF tenta a
   camada de texto; só rasteriza a 300 dpi quando a página não tem texto.

## Licença

CC BY-NC-SA 4.0 — uso e adaptação livres para fins não comerciais, com atribuição.
