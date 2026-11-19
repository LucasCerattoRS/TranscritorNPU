# Mapa do código — Transcritor NPU

Guia para quem vai ler, mudar ou testar o código. O README explica **o que** o app faz e
como instalar; este arquivo explica **como** ele faz. Estado descrito: `main` em `b559438`
(PR #9, aba Baixar + cesta).

## Visão geral

Um único processo Python. O `app.py` monta uma interface **Gradio** (servidor web local em
`127.0.0.1`, o navegador abre sozinho) com quatro abas. Cada botão chama uma função Python
comum; o Gradio faz a ponte entre o navegador e essas funções. Não há banco de dados nem
nuvem: as entradas chegam como caminho de arquivo; transcrições e textos extraídos vão para
`saidas/` e os downloads da aba Baixar, para a pasta escolhida (padrão `saidas/downloads/`).

```
navegador (Gradio)                     app.py                           ferramentas externas
──────────────────                     ──────                           ────────────────────
Áudio / Vídeo  ── Transcrever ──▶ transcrever() ─┬─ baixar_de_url() ──▶ yt-dlp (só o áudio, pasta temporária)
                                                 ├─ carregar_audio() ─▶ ffmpeg (PCM f32 mono 16 kHz, via pipe)
                                                 └─ _gerar_com_retry() ▶ OpenVINO GenAI WhisperPipeline (NPU/GPU/CPU)
Baixar         ── Baixar ───────▶ baixar() ──────── baixar_midia() ───▶ downloader.run_download() ▶ yt-dlp
               ── Baixar e transcrever ▶ baixar_e_transcrever() = baixar_midia() + transcrever()
                                                    └─ _registrar() ───▶ historico.salvar() (JSON por usuário)
Imagem (OCR)   ── Extrair texto ▶ transcrever_imagem() ─────────────────▶ Pillow + Tesseract
PDF → Texto    ── Extrair texto ▶ transcrever_pdf() ── texto nativo ────▶ PyMuPDF; sem texto ▶ 300 dpi + Tesseract
```

## Módulos

| Arquivo | Linhas | Papel |
|---|---|---|
| `app.py` | ~570 | Tudo o que é do app: constantes de pasta, cache de pipelines, decodificação, transcrição, OCR, PDF, aba Baixar, JavaScript injetado e a montagem da UI. |
| `downloader.py` | ~310 | Envoltório do yt-dlp: valida URL, detecta plataforma, monta opções, limita o comprimento do caminho (Windows), traduz erros. Cópia adaptada do repositório irmão `video-downloader` (copiada, não importada, para o app continuar portátil). |
| `historico.py` | ~70 | Histórico de downloads em JSON fora da pasta do app, gravação atômica, limite de 200 itens. Também copiado do `video-downloader`. |
| `estatico/cesta-dropzone.{js,css}` | — | Componente opcional "arremesse o arquivo na cesta" (JS puro, sem dependências). Se os arquivos não existirem, o app abre sem ele. |
| `experimentos-openvino/` | — | Scripts de estudo (ResNet, Phi-3 por CLI e por HTTP). **Não fazem parte do app**; `server.py` e `chat_openvino.py` têm teste de encerramento. |
| `test/` | — | pytest com stubs; ver [Testes](#testes). |
| `iniciar.sh` / `Iniciar Transcritor.bat` | — | Atalhos: rodam `.venv/.../python app.py`. |

### `app.py` por área

| Área | Funções / nomes | O que observar |
|---|---|---|
| Pastas | `PASTA`, `MODELO`, `SAIDAS`, `CACHE` | Relativas ao próprio `app.py`. `saidas/` e `cache/` são criadas **ao importar** o módulo. |
| Tesseract no Windows | bloco `if sys.platform == "win32"` | Só fixa `C:\Program Files\Tesseract-OCR\tesseract.exe` se o `tesseract` não estiver no PATH. |
| Idiomas | `IDIOMAS` (Whisper), `IDIOMAS_OCR` (Tesseract) | Rótulo da UI → código. Whisper recebe `config.language = "<|pt|>"`; "auto" não define idioma. |
| Cache de modelo | `_pipelines`, `_pipeline_lock`, `obter_pipeline`, `invalidar_pipeline` | Um `WhisperPipeline` por dispositivo **pedido**. Se o pedido falha ao carregar, tenta o próximo (NPU→GPU→CPU; GPU→CPU) e guarda o resultado sob a chave do pedido. O lock impede duas cargas simultâneas do mesmo modelo. |
| Recuperação de `DEVICE_LOST` | `_gerar_com_retry` | Se `generate` levanta `RuntimeError` com `DEVICE_LOST`, descarta o pipeline e repete **uma vez**. Um segundo `DEVICE_LOST` sobe para a UI. Vale para qualquer dispositivo, embora o problema conhecido seja o da NPU. |
| Decodificação | `carregar_audio` | `ffmpeg ... -f f32le -` e `np.frombuffer` (sem arquivo temporário). ffmpeg ausente, erro de leitura ou áudio vazio viram `gr.Error` em português. |
| Link na aba Áudio/Vídeo | `_opcoes_yt_dlp`, `baixar_de_url` | Baixa só `bestaudio` numa `TemporaryDirectory`, apagada no `finally` de `transcrever`. Para guardar a mídia, o caminho é a aba Baixar. |
| Login para Instagram | `_opcoes_yt_dlp` | Ordem: `cookies.txt` ao lado do `app.py` (no `.gitignore`) → cookies do Brave (só com o Brave fechado) → sem login. Node.js resolve os desafios JS do YouTube (`js_runtimes`, `remote_components`). |
| Aba Baixar | `baixar_midia`, `baixar`, `baixar_e_transcrever`, `_registrar`, `tabela_historico` | Ver [Fluxo da aba Baixar](#fluxo-da-aba-baixar). |
| Legenda | `_ts_srt`, `gerar_srt` | Arredonda para milissegundos **antes** do `divmod` (evita `00:00:60,000`); trechos só com espaço ficam fora e a numeração continua. |
| Nome de arquivo | `_nome_seguro` | Troca caracteres proibidos no Windows por `_`, conserta bytes não UTF-8 vindos do Linux, corta em 180 bytes UTF-8 sem partir caractere. |
| Transcrição | `transcrever` | Ver [Fluxo da transcrição](#fluxo-da-transcrição). |
| OCR | `transcrever_imagem` | Imagem corrompida e "nenhum texto" viram `gr.Error`; nada é gravado nesses casos. |
| PDF | `transcrever_pdf` | Por página: `get_text()`; se vazio, rasteriza a 300 dpi e passa no Tesseract. PDF corrompido/protegido e PDF sem texto viram `gr.Error`. |
| JS injetado | `COLAR_JS`, `montar_head`, `CESTA_INIT_JS` | Ctrl+V entrega o arquivo colado ao `<input type=file>` visível. A cesta entrega ao input de `#entrada-midia`. `montar_head` recusa CSS/JS que contenha `</script`/`</style` (não deixa o arquivo fechar a tag e injetar HTML). |
| UI | bloco `with gr.Blocks(...)` | Liga cada botão à função: `botao.click(função, [entradas], [saídas])`. |
| Início | `if __name__ == "__main__"` | `app.launch(server_name="127.0.0.1", inbrowser=True, head=montar_head())`: só nesta máquina. |

## Fluxo da transcrição

`transcrever(arquivo, url, dispositivo, idioma_nome)`:

1. Sem arquivo e sem link → `gr.Error`.
2. Só link → `baixar_de_url` numa pasta temporária; o nome base vem do título do vídeo.
3. `carregar_audio` → vetor float32 a 16 kHz; `duracao = amostras / 16000`.
4. `obter_pipeline(dispositivo)` (a primeira carga na NPU compila cache em `cache/` e pode levar minutos).
5. Configura `task = "transcribe"`, `return_timestamps = True` e o idioma.
6. `_gerar_com_retry` → texto + `chunks` com início/fim.
7. Grava `saidas/<base>_<AAAA-MM-DD_HH-MM-SS>_<uuid>.txt` e, se houver trechos, o `.srt` com o mesmo nome. O `uuid4` impede que duas transcrições no mesmo segundo se sobrescrevam.
8. Devolve texto, lista de arquivos e a linha de informação (duração, dispositivo, tempo, "× tempo real").
9. `finally`: apaga a pasta temporária do link, com sucesso ou erro.

## Fluxo da aba Baixar

`baixar_midia(url, modo, qualidade, pasta)`:

1. `downloader.validar_url`: só `http`/`https`, com host, sem espaço nem caractere de controle.
2. Pasta vazia → `saidas/downloads/`; senão `normalizar_pasta` (expande `~`, torna absoluta).
3. Grava no histórico um registro `status: "downloading"` **antes** de baixar.
4. `downloader.run_download(...)` (bloqueante):
   - recusa cedo se precisa de ffmpeg (MP3/legenda) e ele não existe;
   - `build_options` corta o título conforme o comprimento da pasta (`LIMITE_CAMINHO = 250`, limite de caminho do Windows) e levanta `CaminhoLongo` se não cabe nem um título mínimo;
   - `extrair_um_video` resolve o link **sem baixar** e recusa playlist antes de qualquer download;
   - erros do yt-dlp passam por `_friendly_error` (disco cheio, ffmpeg, link inválido, privado, limite de requisições, conexão);
   - devolve `(título, caminho final)`, lido de `requested_downloads` depois do merge/MP3.
5. Atualiza o registro para `ok` (com arquivo) ou `error` (com mensagem) e regrava.

`baixar_e_transcrever` chama `baixar_midia` e depois `transcrever(caminho, ...)`. Se a
transcrição falha, a mídia **continua na pasta** e a mensagem diz onde; a exceção não sobe.

Qualidades: a UI oferece `360p/720p/1080p/Melhor`; `_QUALITY_FORMATS` não tem a chave
`"Melhor"` e cai no padrão `"best"` (`bv*+ba/b`), que é o comportamento desejado.

## Histórico (`historico.py`)

- Local: `$TRANSCRITOR_HISTORICO` se definido (os testes usam); senão
  `%APPDATA%\transcritor-npu\historico.json` (Windows) ou
  `${XDG_DATA_HOME:-~/.local/share}/transcritor-npu/historico.json`.
- `carregar`: arquivo ausente, JSON inválido, aninhado demais ou que não é lista → lista vazia
  (nunca derruba o app). Itens sem `id` são descartados. Itens que ficaram `queued`/`downloading`
  (o app caiu no meio) voltam como `error` "Interrompido".
- `salvar`: arquivo temporário na mesma pasta + `os.replace` (atômico); em erro, apaga o temporário.
- `app._registrar` usa um lock e troca o registro pelo `id` (insere no topo). Falha de disco vira aviso no console; o download segue.

## Regras de negócio e onde estão testadas

| Regra | Código | Teste |
|---|---|---|
| Timestamp SRT nunca mostra 60 s/60 min | `_ts_srt` | `test_srt.py` |
| SRT sem blocos vazios, numeração contínua | `gerar_srt` | `test_srt.py`, `test_fluxo_transcricao.py` |
| Nome de arquivo seguro (Windows, acento, bytes inválidos, 180 bytes) | `_nome_seguro` | `test_srt.py`, `test_saidas.py` |
| Duas saídas no mesmo segundo não se sobrescrevem | carimbo + `uuid4` | `test_saidas.py` |
| Pasta temporária do link some mesmo com erro | `transcrever` (`finally`) | `test_fluxo_transcricao.py` |
| Erro do ffmpeg vira mensagem clara | `carregar_audio` | `test_fluxo_transcricao.py` |
| Modelo ausente → mensagem clara | `obter_pipeline` | `test_auditoria.py` |
| Cargas concorrentes compartilham um pipeline | `_pipeline_lock` | `test_pipeline.py` |
| `DEVICE_LOST` repete uma vez; o segundo sobe; outro erro não repete | `_gerar_com_retry` | `test_estados_vazios.py` |
| Entradas vazias/corrompidas não criam saída | `transcrever_imagem`, `transcrever_pdf` | `test_estados_vazios.py`, `test_auditoria.py` |
| Playlist recusada antes de baixar | `downloader.extrair_um_video` | `test_baixar.py` |
| `%` no nome da pasta não vira campo do template do yt-dlp | `build_options` (também escapado em `baixar_de_url`, sem teste) | `test_baixar.py` |
| Pasta sem permissão vira mensagem, não traceback | `run_download` | `test_baixar.py` |
| Falha na transcrição não perde a mídia baixada | `baixar_e_transcrever` | `test_baixar.py` |
| Histórico: download em andamento vira "Interrompido" ao reabrir | `historico.carregar` | `test_baixar.py` |
| Cesta é opcional e não injeta HTML | `montar_head` | `test_cesta.py` |
| `server.py` e `chat_openvino.py` saem com código ≠ 0 se o modelo não carrega | `experimentos-openvino/` | `test_server_encerramento.py` |

## Testes

```bash
python -m venv .venv
.venv/bin/pip install pytest numpy        # só isso: o resto vira stub
.venv/bin/python -m pytest -q test
```

- `test/conftest.py` coloca `MagicMock` em `sys.modules` para `gradio`, `openvino_genai`,
  `fitz`, `pytesseract`, `yt_dlp` e `PIL` **antes** de qualquer teste importar `app`.
  `gr.Error` vira uma exceção de verdade, para os testes conferirem a mensagem.
- Nenhum teste usa rede, modelo, NPU ou ffmpeg reais. A transcrição real **nunca** é exercitada.
- CI: `.github/workflows/testes.yml`, Python 3.12, `pytest -q test` em todo push e PR.
- **Estado em 19/11/2026:** na `main`, 8 testes falham (55 passam), porque o pytest recente
  recusa `monkeypatch.setattr` em atributo que o `MagicMock` só cria sob demanda (ex.:
  `app.fitz.open`). O PR #10 (`claude/testes-ci-mocks`, aberto) corrige no `conftest.py`; na
  branch dele, 65 passam. Medido localmente com pytest + numpy.

## Como rodar

Ver README (Windows e Linux). Resumo: Python 3.13, `pip install -r requirements.txt`,
ffmpeg e Tesseract no sistema, Node.js para YouTube, modelo
`OpenVINO/whisper-large-v3-turbo-int8-ov` em `modelo/`, `python app.py`. Sem modelo, a UI
abre e a transcrição falha com mensagem clara. O port Linux está em `LINUX.md` e **não foi
validado** na NPU do Fedora.

## Como contribuir

1. Branch nova a partir de `main`; PR pequeno com o que muda e como foi verificado.
2. Rode `pytest -q test` antes de abrir o PR. Mudou comportamento → teste novo com stub (veja `test_fluxo_transcricao.py` como modelo).
3. Mensagens para o usuário em português, via `gr.Error`; nada de traceback cru na tela.
4. Não versione `modelo/`, `cache/`, `saidas/`, `cookies.txt` nem `.venv/` (já no `.gitignore`).
5. `downloader.py` e `historico.py` nasceram de cópias do `video-downloader`: correção que valha
   para os dois deve ser levada para lá também.
6. Funcionou de verdade só quando rodou com o modelo e o dispositivo real; teste com stub prova o fluxo, não a transcrição.

## Pontas soltas conhecidas (não corrigidas aqui)

- `downloader.NoVideoContent` (post de Instagram sem vídeo) cita um fallback `photo_downloader`
  que existe no `video-downloader`, não neste repositório; aqui ele é tratado como
  `DownloadFailed` comum e vira mensagem de erro.
- O cabeçalho de `estatico/cesta-dropzone.css` cita `docs/QUADROS.md`, que não está neste repositório.
- Sem botão de cancelar; arquivo longo é decodificado inteiro para a memória (~230 MB por hora). Ver "Pendências" no README.
