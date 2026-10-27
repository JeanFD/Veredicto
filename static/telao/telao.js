const $ = (id) => document.getElementById(id);
const semMovimento = matchMedia("(prefers-reduced-motion: reduce)").matches;
let sessaoAtual = null;

// ---------- Números animados ----------
const animacoes = new WeakMap();

function contar(el, destino, duracao = 600) {
  const anterior = animacoes.get(el);
  if (anterior) {
    cancelAnimationFrame(anterior.quadro);
    clearTimeout(anterior.garantia);
  }
  const origem = Number(el.textContent) || 0;
  if (semMovimento || origem === destino) {
    el.textContent = destino;
    return;
  }
  const estado = {};
  const inicio = performance.now();
  const passo = (agora) => {
    const t = Math.min((agora - inicio) / duracao, 1);
    el.textContent = Math.round(origem + (destino - origem) * (1 - (1 - t) ** 3));
    if (t < 1) estado.quadro = requestAnimationFrame(passo);
  };
  estado.quadro = requestAnimationFrame(passo);
  // o navegador pausa requestAnimationFrame com a janela coberta: o número certo chega mesmo assim
  estado.garantia = setTimeout(() => {
    cancelAnimationFrame(estado.quadro);
    el.textContent = destino;
  }, duracao + 100);
  animacoes.set(el, estado);
}

function atualizarTotal(total) {
  const el = $("total");
  if (Number(el.textContent) !== total) {
    el.classList.remove("pulso");
    void el.offsetWidth; // reinicia a animação de pulso
    el.classList.add("pulso");
  }
  contar(el, total);
}

// ---------- Estado ----------
function mostrarEstado(m, aoVivo) {
  // só a transição ENCERRADA → REVELADA da mesma sessão tem contagem regressiva
  const revelandoAgora = aoVivo && m.resultado && sessaoAtual?.id === m.sessao?.id
    && sessaoAtual?.estado === "ENCERRADA";
  sessaoAtual = m.sessao;
  $("tema").textContent = m.sessao ? m.sessao.tema : t("telao.aguardando");
  $("pergunta").hidden = !(m.sessao?.total_perguntas > 1);
  if (!$("pergunta").hidden) {
    $("pergunta").textContent = t("comum.pergunta_de", { n: m.sessao.pergunta, total: m.sessao.total_perguntas });
  }
  // o QR some na hora em que a votação fecha, sem esperar a próxima consulta
  if (m.sessao?.estado !== "ABERTA") {
    $("celular").hidden = true;
    codigoNaTela = null;
  } else {
    atualizarQr();
  }
  if (m.resultado) {
    // snapshot (telão aberto ou reconectado depois da revelação): sem contagem regressiva
    if (revelandoAgora) regressiva(() => mostrarResultado(m.resultado));
    else mostrarResultado(m.resultado);
    return;
  }
  // revelada, o resultado fala por si: sem legenda
  const comLegenda = m.sessao && m.sessao.estado !== "REVELADA";
  $("legenda").textContent = comLegenda ? t(`telao.legenda.${m.sessao.estado}`) : "";
  atualizarTotal(m.total);
  $("resultado").hidden = true;
  $("contagem").hidden = false;
}

// 3·2·1 em 1,5s: a revelação não atrasa mais que isso
function regressiva(depois) {
  if (semMovimento) return depois();
  const tela = $("regressiva");
  tela.hidden = false;
  let n = 3;
  const tique = () => {
    if (n === 0) {
      tela.hidden = true;
      return depois();
    }
    tela.innerHTML = "";
    const numero = document.createElement("span");
    numero.textContent = n--;
    tela.appendChild(numero);
    setTimeout(tique, 500);
  };
  tique();
}

function mostrarResultado(opcoes) {
  const soma = opcoes.reduce((s, o) => s + o.votos, 0) || 1;
  const area = $("resultado");
  area.innerHTML = "";
  opcoes.forEach((o, i) => {
    const linha = document.createElement("div");
    linha.className = "barra entrando";
    linha.style.animationDelay = `${i * 0.15}s`;
    const rotulo = document.createElement("span");
    rotulo.textContent = o.rotulo;
    const trilho = document.createElement("div");
    const barra = document.createElement("div");
    barra.className = "preenchimento";
    barra.style.background = o.cor;
    barra.style.transitionDelay = `${0.3 + i * 0.15}s`;
    trilho.appendChild(barra);
    const numero = document.createElement("strong");
    numero.textContent = 0;
    linha.append(rotulo, trilho, numero);
    area.appendChild(linha);
  });
  $("contagem").hidden = true;
  area.hidden = false;
  void area.offsetWidth; // aplica a largura 0 antes de mudar, para a transição acontecer
  opcoes.forEach((o, i) => {
    area.children[i].querySelector(".preenchimento").style.width = `${(o.votos / soma) * 100}%`;
    contar(area.children[i].querySelector("strong"), o.votos, 1200);
  });
}

// ---------- QR do voto por celular ----------
// O mesário abre o telão pelo link do painel (#chave=...); sem a chave, o telão funciona sem QR.
(() => {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("chave")) {
    localStorage.setItem("telao_chave", p.get("chave"));
    history.replaceState(null, "", location.pathname);
  }
})();

let codigoNaTela = null;

async function atualizarQr() {
  const chave = localStorage.getItem("telao_chave");
  if (!chave || !window.QRCode) return;
  try {
    const r = await fetch("/api/telao/codigo", { headers: { "X-Telao-Chave": chave } });
    if (!r.ok) return;
    const { sessao_id, codigo } = await r.json();
    if (codigo === codigoNaTela) return;
    codigoNaTela = codigo;
    const area = $("qr");
    area.innerHTML = "";
    $("celular").hidden = !codigo;
    if (codigo) {
      const link = `${location.origin}/celular/#s=${sessao_id}&c=${codigo}`;
      new QRCode(area, { text: link, width: 240, height: 240, correctLevel: QRCode.CorrectLevel.M });
    }
  } catch {
    // sem rede: mantém o último QR; o código antigo ainda vale por até 30s
  }
}

function conectar() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/telao`);
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.tipo === "snapshot" || m.tipo === "estado") mostrarEstado(m, m.tipo === "estado");
    if (m.tipo === "total" && sessaoAtual && m.sessao_id === sessaoAtual.id) {
      atualizarTotal(m.total);
    }
  };
  ws.onclose = () => setTimeout(conectar, 2000);
}

conectar();
atualizarQr();
// o código muda a cada 30s; buscar a cada 5s mantém o QR sempre na janela atual
setInterval(atualizarQr, 5000);
