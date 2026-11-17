"""A cesta é opcional: sem os arquivos em estatico/, o app usa só o colar (Ctrl+V)."""
import os

import app


def test_head_com_cesta_inclui_script_estilo_e_alvo():
    head = app.montar_head()
    assert head.startswith(app.COLAR_JS)
    assert "CestaDropzone" in head and "<style>" in head
    assert "#entrada-midia input[type=file]" in head and "cesta-midia" in head


def test_head_sem_arquivos_cai_no_colar(tmp_path):
    assert app.montar_head(str(tmp_path)) == app.COLAR_JS


def test_head_recusa_arquivo_que_fecha_a_tag(tmp_path):
    (tmp_path / "cesta-dropzone.css").write_text("a{}", encoding="utf-8")
    (tmp_path / "cesta-dropzone.js").write_text("x='</script><script>alert(1)'", encoding="utf-8")
    assert app.montar_head(str(tmp_path)) == app.COLAR_JS


def test_arquivos_da_cesta_estao_no_repo():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "estatico")
    for nome in ("cesta-dropzone.js", "cesta-dropzone.css"):
        assert os.path.getsize(os.path.join(base, nome)) > 1000
