const $ = (id) => document.getElementById(id);
const semMovimento = matchMedia("(prefers-reduced-motion: reduce)").matches;
let sessaoAtual = null;

const LEGENDAS = {
  AGUARDANDO: "votação ainda não aberta",
  ABERTA: "votos registrados",
  ENCERRADA: "votação encerrada · aguardando revelação",
};

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
  $("tema").textContent = m.sessao ? m.sessao.tema : "Aguardando";
  if (m.resultado) {
    // snapshot (telão aberto ou reconectado depois da revelação): sem contagem regressiva
    if (revelandoAgora) regressiva(() => mostrarResultado(m.resultado));
    else mostrarResultado(m.resultado);
    return;
  }
  $("legenda").textContent = (m.sessao && LEGENDAS[m.sessao.estado]) || "";
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
