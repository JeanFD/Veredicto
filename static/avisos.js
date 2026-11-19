// Avisos do painel: uma pilha de recados no canto da tela, no lugar dos alert(), que
// travavam o painel inteiro, exigiam um clique para qualquer coisa seguir e sumiam
// sem deixar rastro. Durante uma sessão ao vivo isso custa caro.
//
//   avisarFeito(texto) — deu certo; some sozinho.
//   avisar(texto)      — recado; some sozinho.
//   avisarErro(texto)  — deu errado; fica na tela até alguém fechar.
//
// O leitor de tela ouve todos: a pilha é uma região aria-live, e o erro, por ser
// role="alert", é anunciado na hora. O mesmo texto repetido não empilha — o aviso
// que já está na tela ganha um contador, para a reconexão em laço não virar parede.
(() => {
  const SUMIR_EM = 6000;
  const MAXIMO = 4;
  const relogios = new WeakMap();
  let area = null;

  function areaDeAvisos() {
    if (!area) {
      area = document.createElement("div");
      area.id = "avisos";
      area.setAttribute("aria-live", "polite");
      document.body.appendChild(area);
    }
    return area;
  }

  function programarSaida(aviso) {
    clearTimeout(relogios.get(aviso));
    // erro fica: quem está conduzindo a sessão precisa poder ler com calma
    if (aviso.dataset.tipo === "erro") return;
    relogios.set(aviso, setTimeout(() => aviso.remove(), SUMIR_EM));
  }

  function contarDeNovo(aviso) {
    const vezes = Number(aviso.dataset.vezes ?? 1) + 1;
    aviso.dataset.vezes = vezes;
    const marca = aviso.querySelector(".vezes");
    marca.textContent = `${vezes}×`;
    marca.hidden = false;
    programarSaida(aviso);
  }

  function montar(texto, tipo) {
    const aviso = document.createElement("div");
    aviso.className = `aviso ${tipo}`;
    aviso.dataset.tipo = tipo;
    aviso.dataset.texto = texto;
    if (tipo === "erro") aviso.setAttribute("role", "alert");

    const corpo = document.createElement("p");
    corpo.textContent = texto;
    const vezes = document.createElement("span");
    vezes.className = "vezes";
    vezes.hidden = true;
    const fechar = document.createElement("button");
    fechar.type = "button";
    fechar.textContent = "×";
    fechar.setAttribute("aria-label", t("comum.fechar"));
    fechar.onclick = () => aviso.remove();

    aviso.append(corpo, vezes, fechar);
    return aviso;
  }

  window.avisar = (texto, tipo = "info") => {
    if (!texto) return;
    const area = areaDeAvisos();
    const repetido = [...area.children].find((a) => a.dataset.texto === texto);
    if (repetido) return contarDeNovo(repetido);
    area.appendChild(montar(texto, tipo));
    while (area.children.length > MAXIMO) area.firstElementChild.remove();
    programarSaida(area.lastElementChild);
  };

  window.avisarFeito = (texto) => avisar(texto, "ok");
  window.avisarErro = (texto) => avisar(texto, "erro");
})();
