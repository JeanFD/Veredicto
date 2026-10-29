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
