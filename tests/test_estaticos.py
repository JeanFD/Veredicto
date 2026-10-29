import re
from pathlib import Path

import pytest

@pytest.mark.parametrize("caminho", ["/", "/i18n.js", "/estilo.css", "/mesario/", "/urna/urna.js"])
def test_estaticos_sempre_revalidados(cliente, caminho):
    """Depois de um deploy o navegador não pode juntar HTML novo com JS antigo."""
    r = cliente.get(caminho)
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-cache"
    # sem mudança, a revalidação é um 304 sem corpo
    r2 = cliente.get(caminho, headers={"If-None-Match": r.headers["ETag"]})
    assert r2.status_code == 304 and r2.headers["Cache-Control"] == "no-cache"

def test_html_pede_js_e_css_com_versao():
    """Quem abriu o site antes do no-cache tem cópias velhas: a ?v= é uma URL que nenhum cache tem."""
    for html in Path("static").rglob("*.html"):
        for ref in re.findall(r'(?:src|href)="(?!https?:)([^"]+\.(?:js|css)(?:\?[^"]*)?)"', html.read_text(encoding="utf-8")):
            assert re.search(r"\?v=\d+$", ref), (html, ref)
