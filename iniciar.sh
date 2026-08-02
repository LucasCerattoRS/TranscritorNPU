#!/usr/bin/env bash
# Equivalente Linux do "Iniciar Transcritor.bat".
#
# Pre-requisitos de sistema (ver LINUX.md pro roteiro completo):
#   sudo dnf install ffmpeg tesseract tesseract-langpack-por
#   python -m venv .venv && .venv/bin/pip install -r requirements.txt
# A pasta modelo/ (Whisper em formato OpenVINO IR) precisa ser copiada do
# Windows -- e' portavel, nao precisa reconverter.
set -e
cd "$(dirname "$0")"

echo "Iniciando o Transcritor NPU... o navegador abre sozinho quando estiver pronto."
exec .venv/bin/python app.py
