// Confirmações do painel, no lugar dos confirm() e prompt() do navegador. Aqueles
// davam o mesmo "OK / Cancelar" para abrir uma votação e para apagar uma sessão, não
// diziam o que ia acontecer e punham o foco no botão que confirma.
//
//   await confirmar({ titulo, texto, acao, perigo, campo, digitar })
//
// Devolve null quando a pessoa desiste; quando ela confirma, devolve o que foi
// digitado (string vazia se não houver campo). O foco começa em "Cancelar" e Esc
// fecha, então o caminho sem querer é sempre o que não faz nada.
//
//   texto   — parágrafos separados por quebra de linha; diz o que vai acontecer.
//   acao    — o que o botão faz ("Revelar resultado"), nunca "OK".
//   perigo  — pinta o botão de vermelho: não tem volta.
//   campo   — { rotulo, valor, tipo } para pedir um valor, como o antigo prompt.
//   digitar — exige digitar este texto para liberar o botão (apagar, zerar).
(() => {
  function paragrafos(texto) {
    return String(texto ?? "").split("\n").filter(Boolean).map((linha) => {
      const p = document.createElement("p");
      p.textContent = linha;
      return p;
    });
  }

  function campoDeTexto({ rotulo, valor = "", tipo = "text" }) {
    const marca = document.createElement("label");
    marca.className = "campo";
    const nome = document.createElement("span");
    nome.textContent = rotulo;
    const entrada = document.createElement("input");
    entrada.type = tipo;
    entrada.value = valor;
    marca.append(nome, entrada);
    return { marca, entrada };
  }

  window.confirmar = ({ titulo, texto, acao, perigo, campo, digitar }) => new Promise((resolve) => {
    const dialogo = document.createElement("dialog");
    dialogo.className = "pergunta-modal";
    const formulario = document.createElement("form");
    formulario.method = "dialog";

    const cabeca = document.createElement("h2");
    cabeca.textContent = titulo;
    formulario.append(cabeca, ...paragrafos(texto));

    let entrada = null;
    if (campo || digitar) {
      const pedido = campo ?? { rotulo: t("mesario.digite_para_confirmar", { texto: digitar }) };
      const feito = campoDeTexto(pedido);
      entrada = feito.entrada;
      formulario.append(feito.marca);
    }

    const linha = document.createElement("div");
    linha.className = "linha-form fim";
    const desistir = document.createElement("button");
    desistir.type = "button";
    desistir.textContent = t("comum.cancelar");
    desistir.autofocus = true;
    const seguir = document.createElement("button");
    seguir.value = "sim";
    seguir.textContent = acao;
    seguir.className = perigo ? "perigo" : "principal";
    linha.append(desistir, seguir);
    formulario.append(linha);
    dialogo.append(formulario);

    // o botão só libera quando o texto pedido for digitado por inteiro
    if (digitar) {
      seguir.disabled = true;
      entrada.oninput = () => { seguir.disabled = entrada.value.trim() !== digitar; };
    }
    desistir.onclick = () => dialogo.close("");
    dialogo.addEventListener("close", () => {
      dialogo.remove();
      resolve(dialogo.returnValue === "sim" ? entrada?.value ?? "" : null);
    });

    document.body.append(dialogo);
    dialogo.showModal();
  });
})();
