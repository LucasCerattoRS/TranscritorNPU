# Port pro Linux (Fedora) — conceito, não implementado ainda

Documento de planejamento. Nada aqui foi executado; é o roteiro pra quando decidirmos
rodar o Transcritor NPU no lado Fedora do dual boot em vez do Windows.

## Por que é viável

A NPU (Intel AI Boost) **não é exclusiva do Windows**. Duas peças já existem prontas do lado Intel:

- **Driver de kernel `intel_vpu`**: upstream no kernel Linux desde a 6.8 (via `drivers/accel/ivpu`).
  Se o kernel do Fedora já for >= 6.8, o módulo já pode estar disponível sem compilar nada.
- **Runtime userspace + OpenVINO**: a Intel mantém o [`linux-npu-driver`](https://github.com/intel/linux-npu-driver)
  (level-zero + firmware loader) e o OpenVINO 2026 documenta NPU no Linux como plataforma de
  primeira classe, não experimental.

O `app.py` em si (Python + Gradio + ffmpeg + pytesseract + yt-dlp) já é 100% cross-platform —
nenhuma linha de código muda. O trabalho é todo de sistema operacional/driver.

## Passo a passo (quando for fazer)

1. **Checar o kernel do Fedora**: `uname -r`. Se >= 6.8, rodar `lsmod | grep ivpu` e
   `ls /dev/accel/` pra ver se o dispositivo já aparece sozinho.
2. **Instalar o driver userspace**: pacote `intel-npu-driver` (disponível via Snap no Fedora,
   ou compilar do [repo oficial](https://github.com/intel/linux-npu-driver/releases)).
3. **Permissões**: adicionar o usuário ao grupo que tem acesso a `/dev/accel/accel0`
   (normalmente `render`), senão o Python só enxerga a NPU rodando como root.
4. **Ambiente Python**: mesmo fluxo do Windows —
   `python -m venv .venv && pip install -r requirements.txt`. Os pacotes
   (`gradio`, `openvino-genai`, `pytesseract`, `yt-dlp`, `Pillow`) têm wheel pra Linux.
5. **Dependências de sistema equivalentes ao que foi instalado no Windows**:
   - `ffmpeg` → `sudo dnf install ffmpeg` (via RPM Fusion)
   - Tesseract OCR → `sudo dnf install tesseract tesseract-langpack-por`
   - Node.js (usado pelo yt-dlp pra resolver desafios JS do YouTube) → já costuma
     estar disponível via `dnf` ou `nvm`
6. **Reusar o modelo**: a pasta `modelo/` (formato OpenVINO IR) é portável entre SOs —
   não precisa reconverter/reexportar o Whisper. Só copiar a pasta pro Fedora.
7. **Validar**: rodar `openvino_genai.WhisperPipeline(..., "NPU")` num script pequeno antes
   de tentar a UI inteira, pra isolar erro de driver de erro de app.

## Riscos / pontos de atenção

- **Secure Boot fica ligado** ([[dual-boot-fedora]], decisão já tomada e não deve mudar).
  Isso não deveria travar o driver: o módulo `ivpu` in-tree já vem assinado pelo Fedora.
  Só viraria problema se algum dia for preciso compilar um módulo de kernel fora da árvore
  (nesse caso entra MOK enrollment) — não é o caso do driver Intel documentado hoje.
- **Geração de CPU**: a NPU só existe em Core Ultra (Meteor Lake em diante). Confirmar que
  o driver oficial lista o chip específico da máquina como suportado antes de gastar tempo.
- **Firmware da NPU**: o `linux-npu-driver` baixa/instala firmware específico por geração;
  vale conferir a versão certa pro chip antes de instalar.
- Sem GPU Arc testada no Linux ainda — o fallback "GPU" do app pode não funcionar de cara
  mesmo com a NPU ok; teria que validar separado.

## O que fica pra depois

Este documento só organiza a ideia. Próxima ação concreta (quando o Lukas decidir) é rodar
o passo 1 (checar kernel/driver) no Fedora e reportar o resultado antes de instalar mais nada.
