// Texto preto ou branco conforme a cor de fundo.
//
// A cor de cada opção sai de um seletor livre no painel, e o texto era sempre branco:
// um amarelo claro escolhido sem querer deixava o rótulo ilegível na urna, justamente
// na tela em que a pessoa escolhe o voto. Aqui a luminância relativa da WCAG decide,
// e vence a cor que tiver mais contraste com o fundo.
(() => {
  const ESCURO = "#0b1424";
  const CLARO = "#ffffff";

  function canal(byte) {
    const c = byte / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }

  function luminancia(cor) {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(cor.slice(i, i + 2), 16));
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b);
  }

  const contraste = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

  window.corDoTexto = (fundo) => {
    // o seletor sempre devolve #rrggbb; qualquer outra coisa fica no branco de antes
    if (!/^#[0-9a-f]{6}$/i.test(fundo ?? "")) return CLARO;
    const luz = luminancia(fundo);
    return contraste(luz, luminancia(ESCURO)) >= contraste(luz, luminancia(CLARO)) ? ESCURO : CLARO;
  };
})();
