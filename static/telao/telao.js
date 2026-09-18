const $ = (id) => document.getElementById(id);
let sessaoAtual = null;

function mostrarEstado(m) {
  sessaoAtual = m.sessao;
  $("tema").textContent = m.sessao ? m.sessao.tema : "Aguardando";
  $("total").textContent = m.total;
  if (m.resultado) {
    mostrarResultado(m.resultado);
  } else {
    $("resultado").hidden = true;
    $("contagem").hidden = false;
  }
}

function mostrarResultado(opcoes) {
  const soma = opcoes.reduce((s, o) => s + o.votos, 0) || 1;
  const area = $("resultado");
  area.innerHTML = "";
  for (const o of opcoes) {
    const linha = document.createElement("div");
    linha.className = "barra";
    const rotulo = document.createElement("span");
    rotulo.textContent = o.rotulo;
    const trilho = document.createElement("div");
    const barra = document.createElement("div");
    barra.className = "preenchimento";
    barra.style.background = o.cor;
    barra.style.width = "0%";
    trilho.appendChild(barra);
    const numero = document.createElement("strong");
    numero.textContent = o.votos;
    linha.append(rotulo, trilho, numero);
    area.appendChild(linha);
    requestAnimationFrame(() => { barra.style.width = `${(o.votos / soma) * 100}%`; });
  }
  $("contagem").hidden = true;
  area.hidden = false;
}

function conectar() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/telao`);
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.tipo === "snapshot" || m.tipo === "estado") mostrarEstado(m);
    if (m.tipo === "total" && sessaoAtual && m.sessao_id === sessaoAtual.id) {
      $("total").textContent = m.total;
    }
  };
  ws.onclose = () => setTimeout(conectar, 2000);
}

conectar();