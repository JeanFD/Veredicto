// Urna sem configuração: pede ao servidor um código curto, mostra na tela e espera o
// mesário aprovar no painel. Aprovada, recebe id e token e recarrega já como urna.
// O pedido fica no localStorage: recarregar a página continua esperando o mesmo código.
window.parear = (() => {
  const el = (id) => document.getElementById(id);
  const CHAVE = "pedido_urna";
  let volta = null;

  function mostrar(titulo, ajuda) {
    el("tema").textContent = titulo;
    el("tema").classList.remove("codigo-pedido");
    el("pergunta").textContent = ajuda ?? "";
    el("pergunta").hidden = !ajuda;
    el("opcoes").innerHTML = "";
  }

  function oferecer(aviso) {
    mostrar(t("urna.parear_titulo"), aviso);
    const b = document.createElement("button");
    b.textContent = t("urna.parear_pedir");
    b.style.background = "#2563eb";
    b.onclick = pedir;
    el("opcoes").appendChild(b);
  }

  async function pedir() {
    mostrar(t("comum.enviando"));
    try {
      const r = await fetch("/api/urnas/pedido", { method: "POST" });
      const dados = await r.json();
      if (!r.ok) return oferecer(dados.detail?.mensagem ?? t("urna.parear_erro"));
      localStorage.setItem(CHAVE, JSON.stringify({ segredo: dados.segredo, codigo: dados.codigo }));
      aguardar();
    } catch {
      oferecer(t("urna.parear_erro"));
    }
  }

  function esquecer(aviso) {
    clearInterval(volta);
    localStorage.removeItem(CHAVE);
    oferecer(aviso);
  }

  async function conferir(segredo) {
    let r;
    try {
      r = await fetch("/api/urnas/pedido/situacao", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segredo }),
      });
    } catch {
      return; // sem rede: tenta na próxima volta
    }
    if (r.status === 404) return esquecer(t("urna.parear_recusado"));
    if (!r.ok) return;
    const dados = await r.json();
    if (!dados.aprovado) return;
    clearInterval(volta);
    localStorage.setItem("urna_id", dados.id);
    localStorage.setItem("urna_token", dados.token);
    localStorage.removeItem(CHAVE);
    location.reload();
  }

  function aguardar() {
    const { segredo, codigo } = JSON.parse(localStorage.getItem(CHAVE));
    mostrar(codigo, t("urna.parear_aguarde"));
    el("tema").classList.add("codigo-pedido");
    const cancelar = document.createElement("button");
    cancelar.textContent = t("urna.parear_cancelar");
    cancelar.className = "secundario";
    cancelar.onclick = () => esquecer();
    el("opcoes").appendChild(cancelar);
    clearInterval(volta);
    volta = setInterval(() => conferir(segredo), 2000);
    conferir(segredo);
  }

  return () => (localStorage.getItem(CHAVE) ? aguardar() : oferecer());
})();
