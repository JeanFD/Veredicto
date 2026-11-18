"""Trazer uma notícia por link: baixa a página e tira dela a manchete e o texto.

O mesário revisa o que veio antes de salvar o cartão. Página com paywall ou feita só
em JavaScript pode vir vazia; nesse caso o texto é colado à mão, como sempre.

Quem busca é o servidor, então a busca é curta e fechada: só http e https, nunca um
endereço interno da máquina (que divide a VPS com outros serviços), poucos
redirecionamentos e limites de tempo e de tamanho.
"""
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

LIMITE_BYTES = 2 * 1024 * 1024
LIMITE_SEGUNDOS = 10
MAX_REDIRECIONAMENTOS = 3
LIMITE_TEXTO = 4000

# fora do texto: menu, rodapé, scripts e afins
IGNORADAS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "figure", "svg", "button"}
BLOCOS = {"p", "h1", "h2", "h3", "li", "blockquote"}
CURTOS = {"h1", "h2", "h3", "li"}  # título de seção e tópico valem mesmo curtos


class EnderecoRecusado(ValueError):
    """O motivo vira a mensagem mostrada ao mesário (ver app/i18n.py)."""


def conferir_endereco(url: str):
    partes = urlparse(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise EnderecoRecusado("endereco_invalido")
    porta = partes.port or (443 if partes.scheme == "https" else 80)
    try:
        enderecos = socket.getaddrinfo(partes.hostname, porta, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise EnderecoRecusado("endereco_nao_encontrado")
    # is_global deixa de fora localhost, redes privadas e os endereços reservados
    if any(not ipaddress.ip_address(endereco[4][0]).is_global for endereco in enderecos):
        raise EnderecoRecusado("endereco_interno")


async def baixar(url: str) -> str:
    """O HTML da página, conferindo o endereço a cada redirecionamento."""
    cabecalhos = {"User-Agent": "Veredicto/1.0 (juri simulado)", "Accept": "text/html"}
    async with httpx.AsyncClient(follow_redirects=False, timeout=LIMITE_SEGUNDOS, headers=cabecalhos) as http:
        for _ in range(MAX_REDIRECIONAMENTOS + 1):
            conferir_endereco(url)
            async with http.stream("GET", url) as resposta:
                if resposta.is_redirect:
                    url = urljoin(url, resposta.headers.get("location", ""))
                    continue
                resposta.raise_for_status()
                if "html" not in resposta.headers.get("content-type", "text/html"):
                    raise EnderecoRecusado("pagina_nao_html")
                conteudo = b""
                async for pedaco in resposta.aiter_bytes():
                    conteudo += pedaco
                    if len(conteudo) >= LIMITE_BYTES:
                        break
                return conteudo.decode(resposta.encoding or "utf-8", "replace")
    raise EnderecoRecusado("muitos_redirecionamentos")


class Leitor(HTMLParser):
    """Junta os blocos de texto da página e guarda onde começa e acaba o artigo."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.og_titulo = ""     # manchete declarada pela própria página
        self.titulo_aba = ""    # <title>: costuma trazer o nome do site junto
        self.blocos: list[tuple[str, str]] = []
        self.artigo: tuple[int, int] | None = None
        self.ignorando = 0
        self.tag = None
        self.pedacos: list[str] = []
        self.no_titulo = False
        self.abertura_artigo = None
        self.profundidade = 0

    def fechar_bloco(self):
        texto = " ".join("".join(self.pedacos).split())
        if texto:
            self.blocos.append((self.tag, texto))
        self.pedacos, self.tag = [], None

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "meta" and atributos.get("property") == "og:title":
            self.og_titulo = self.og_titulo or " ".join(atributos.get("content", "").split())
        if tag == "title":
            self.no_titulo = True
        if tag in IGNORADAS:
            self.ignorando += 1
        if self.ignorando:
            return
        if tag == "article" and self.abertura_artigo is None:
            self.abertura_artigo, self.profundidade = len(self.blocos), 0
        elif tag == "article":
            self.profundidade += 1
        if tag in BLOCOS:
            self.fechar_bloco()
            self.tag = tag

    def handle_endtag(self, tag):
        if tag == "title":
            self.no_titulo = False
        if tag in IGNORADAS:
            self.ignorando = max(0, self.ignorando - 1)
            return
        if tag == self.tag:
            self.fechar_bloco()
        if tag == "article" and self.abertura_artigo is not None and self.artigo is None:
            if self.profundidade:
                self.profundidade -= 1
            else:
                self.artigo = (self.abertura_artigo, len(self.blocos))

    def handle_data(self, dados):
        if self.no_titulo:
            self.titulo_aba = self.titulo_aba or " ".join(dados.split())
        if self.tag and not self.ignorando:
            self.pedacos.append(dados)


def extrair(html: str, url: str = "") -> dict:
    """Manchete e texto da página, em parágrafos e tópicos prontos para o cartão."""
    leitor = Leitor()
    leitor.feed(html)
    leitor.fechar_bloco()
    blocos = leitor.blocos
    # tendo um <article> com corpo de verdade, o resto da página é descarte
    if leitor.artigo:
        do_artigo = blocos[leitor.artigo[0]:leitor.artigo[1]]
        if sum(len(t) for _, t in do_artigo) >= 200:
            blocos = do_artigo

    titulo = leitor.og_titulo or next((t for tag, t in blocos if tag == "h1"), "") or leitor.titulo_aba
    linhas, vistos = [], set()
    for tag, texto in blocos:
        if texto == titulo or texto in vistos:
            continue
        if len(texto) < (15 if tag in CURTOS else 40):
            continue
        vistos.add(texto)
        linhas.append(f"- {texto}" if tag == "li" else texto)

    texto = "\n\n".join(linhas)
    if len(texto) > LIMITE_TEXTO:  # corta no fim de um parágrafo, não no meio de uma frase
        texto = texto[:LIMITE_TEXTO].rsplit("\n\n", 1)[0]
    return {"titulo": titulo[:120], "texto": texto, "fonte": url}
