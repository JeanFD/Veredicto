# Testes de ponta a ponta

Sobem um servidor uvicorn de verdade, com banco temporário, e dirigem a urna, o
telão e o painel do mesário num Chromium headless.

```bash
pip install -r requirements-e2e.txt
playwright install chromium
pytest e2e
```

Para ver o navegador: `pytest e2e --headed --slowmo 300`.

O `pytest` sem argumentos roda só os testes de backend (`tests/`).
