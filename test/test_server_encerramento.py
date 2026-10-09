"""Testes sinteticos de experimentos-openvino/server.py: sem modelo, sem rede, sem chaves.

As dependencias pesadas (fastapi, pydantic, uvicorn, optimum, transformers) sao
substituidas por stubs em sys.modules; so o fluxo de inicio/erro do modulo roda.
"""
import runpy
import sys
import types
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parent.parent / "experimentos-openvino" / "server.py"


def _stub(monkeypatch, name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, mod)


def _instala_stubs(monkeypatch, from_pretrained):
    class FakeApp:
        def __init__(self, **kw):
            pass

        def post(self, path):
            return lambda f: f

    _stub(monkeypatch, "uvicorn", run=lambda *a, **k: None)
    _stub(monkeypatch, "fastapi", FastAPI=FakeApp, HTTPException=Exception)
    _stub(monkeypatch, "pydantic", BaseModel=object)
    _stub(monkeypatch, "optimum")
    _stub(monkeypatch, "optimum.intel")
    _stub(monkeypatch, "optimum.intel.openvino",
          OVModelForCausalLM=types.SimpleNamespace(from_pretrained=from_pretrained))
    _stub(monkeypatch, "transformers",
          AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a, **k: object()),
          pipeline=lambda *a, **k: object())


def test_falha_ao_carregar_modelo_sai_com_codigo_diferente_de_zero(monkeypatch, capsys):
    def falha(*a, **k):
        raise RuntimeError("sem GPU")

    _instala_stubs(monkeypatch, falha)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SERVER), run_name="server")
    assert exc.value.code not in (None, 0)
    assert "sem GPU" in capsys.readouterr().err


def test_carga_ok_nao_encerra_e_expoe_app(monkeypatch):
    _instala_stubs(monkeypatch, lambda *a, **k: object())
    ns = runpy.run_path(str(SERVER), run_name="server")
    assert "app" in ns and "pipe" in ns
