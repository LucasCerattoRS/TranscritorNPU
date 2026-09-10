# Experimentos OpenVINO

Scripts soltos que viviam sem versionamento em `~/Projetos/openvino` no Fedora.
Guardados aqui em 09/09/2026 porque é o repositório do projeto ao qual pertencem
(inferência local acelerada no Core Ultra 5 125H).

| Arquivo | O que faz |
|---|---|
| `hello_openvino.py` | Classificação de imagem com ResNet-50 (IR `.xml`/`.bin`) — o "olá mundo" do runtime. |
| `chat_openvino.py` | Chat de linha de comando com `Phi-3-mini-4k-instruct-int4-ov` via `optimum.intel.openvino`. |
| `server.py` | O mesmo modelo servido por HTTP (FastAPI + uvicorn). |

**Os pesos não estão aqui.** `resnet50.xml` (286 KB), `resnet50.bin` (21 MB),
`imagenet_2012.txt` e `imagem_teste.jpg` continuam só em `~/Projetos/openvino` —
são download, não código, e podem ser baixados de novo.

**`DEVICE`**: os três scripts estão em `"GPU"`. Se der erro de driver, troque por
`"CPU"`, que é estável no Core Ultra.
