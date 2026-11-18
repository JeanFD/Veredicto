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
  mostrarTotalDoRodape(total);
  const el = $("total");
  if (Number(el.textContent) !== total) {
    el.classList.remove("pulso");
    void el.offsetWidth; // reinicia a animação de pulso
    el.classList.add("pulso");
  }
  contar(el, total);
}

// Cabeçalho e rodapé: a situação da apuração e o total, sempre à vista.
function mostrarMoldura(m) {
  const estado = m.sessao?.estado;
  const situacao = t(`telao.situacao.${estado ?? "AGUARDANDO"}`);
  $("situacao").textContent = situacao;
  $("situacao").classList.toggle("apurado", estado === "REVELADA");
  $("rodape-estado").textContent = situacao;
  $("rodape-caso").textContent = m.sessao?.caso ?? "";
  mostrarTotalDoRodape(m.total ?? 0, m.resultado);
}

function mostrarTotalDoRodape(total, resultado) {
  const votos = t(total === 1 ? "telao.um_voto" : "telao.n_votos", { n: total.toLocaleString(document.documentElement.lang) });
  const pontos = resultado?.reduce((s, o) => s + o.pontos, 0);
  const ponderado = resultado?.some((o) => o.pontos !== o.votos);
  $("rodape-total").textContent = ponderado ? `${votos} · ${t("telao.n_pontos", { n: pontos })}` : votos;
}

// ---------- Cartões ----------
// Pano de fundo do caso, notícia ou laudo que o mesário manda para a tela. O texto
// vem em parágrafos separados por linha em branco; linha começada com "- " é tópico.
function blocosDoTexto(texto) {
  return texto.split(/\n{2,}/).map((parte) => {
    const linhas = parte.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!linhas.length) return null;
    if (linhas.every((l) => l.startsWith("- "))) {
      const lista = document.createElement("ul");
      for (const linha of linhas) {
        const item = document.createElement("li");
        item.textContent = linha.slice(2);
        lista.appendChild(item);
      }
      return lista;
    }
    const paragrafo = document.createElement("p");
    paragrafo.textContent = linhas.join(" ");
    return paragrafo;
  }).filter(Boolean);
}

function dominio(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function mostrarCartao(cartao) {
  document.body.classList.toggle("com-cartao", Boolean(cartao));
  $("cartao").hidden = !cartao;
  if (!cartao) return;
  $("cartao-titulo").textContent = cartao.titulo;
  $("cartao-texto").replaceChildren(...blocosDoTexto(cartao.texto));
  $("cartao").classList.toggle("longo", cartao.texto.length > 1200);
  $("cartao-fonte").hidden = !cartao.fonte;
  $("cartao-fonte").textContent = cartao.fonte ? t("telao.fonte", { fonte: dominio(cartao.fonte) }) : "";
}

// ---------- Cronômetro das falas ----------
// O servidor manda quanto falta e reenvia a cada poucos segundos; entre uma mensagem
// e outra a tela conta sozinha. Zerado o tempo, o relógio vira vermelho e passa a
// mostrar quanto já passou, com um apito na virada.
let cronometro = { visivel: false };
let tiqueCronometro = null;
let apitou = false;

function formatarTempo(restante) {
  const s = restante >= 0 ? Math.ceil(restante) : Math.floor(-restante);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function apitar() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const oscilador = ctx.createOscillator();
    const ganho = ctx.createGain();
    oscilador.frequency.value = 880;
    ganho.gain.setValueAtTime(0.25, ctx.currentTime);
    ganho.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.7);
    oscilador.connect(ganho).connect(ctx.destination);
    oscilador.start();
    oscilador.stop(ctx.currentTime + 0.7);
    setTimeout(() => ctx.close(), 1000);
  } catch {
    // navegador sem áudio ou sem permissão: o vermelho na tela já avisa
  }
}

function mostrarCronometro(c) {
  cronometro = { ...c, recebido: performance.now() };
  desenharCronometro();
  clearInterval(tiqueCronometro);
  if (c.visivel && c.rodando) tiqueCronometro = setInterval(desenharCronometro, 200);
}

function desenharCronometro() {
  const c = cronometro;
  $("cronometro").hidden = !c.visivel;
  if (!c.visivel) return;
  const restante = c.rodando ? c.restante - (performance.now() - c.recebido) / 1000 : c.restante;
  const esgotado = restante < 0;
  $("cronometro-titulo").textContent = c.titulo;
  $("cronometro-tempo").textContent = (esgotado ? "+" : "") + formatarTempo(restante);
  $("cronometro").classList.toggle("esgotado", esgotado);
  $("cronometro-esgotado").hidden = !esgotado;
  if (esgotado && !apitou) apitar();
  apitou = esgotado;
}

// ---------- Estado ----------
function mostrarEstado(m, aoVivo) {
  // só a transição ENCERRADA → REVELADA da mesma sessão tem contagem regressiva
  const revelandoAgora = aoVivo && m.resultado && sessaoAtual?.id === m.sessao?.id
    && sessaoAtual?.estado === "ENCERRADA";
  sessaoAtual = m.sessao;
  $("faixa-teste").hidden = !m.sessao?.teste;
  $("tema").textContent = m.sessao ? m.sessao.tema : t("telao.aguardando");
  $("caso").hidden = !m.sessao?.caso;
  $("caso").textContent = m.sessao?.caso ?? "";
  mostrarMoldura(m);
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

// Com pesos diferentes, as barras e o vencedor seguem os pontos (soma dos pesos), e
// cada opção mostra também quantas pessoas votaram; com todos os pesos 1, são iguais.
function cartaoDaOpcao(o, i, soma, vencedora, ponderado) {
  const cartao = document.createElement("article");
  cartao.className = "opcao" + (o === vencedora ? " vencedora" : "");
  cartao.style.animationDelay = `${0.15 + i * 0.12}s`;

  const cabeca = document.createElement("div");
  cabeca.className = "cabeca";
  const indice = document.createElement("span");
  indice.textContent = String(i + 1).padStart(2, "0");
  cabeca.append(indice);
  if (o === vencedora) {
    const selo = document.createElement("span");
    selo.className = "selo-vencedora";
    selo.textContent = t("telao.vencedora");
    cabeca.append(selo);
  }

  const rotulo = document.createElement("h2");
  rotulo.className = "rotulo";
  rotulo.textContent = o.rotulo;

  const numeros = document.createElement("div");
  numeros.className = "numeros";
  const porcento = document.createElement("strong");
  porcento.className = "porcento";
  const valor = document.createElement("span");
  valor.className = "valor";
  valor.textContent = 0;
  const sinal = document.createElement("span");
  sinal.className = "sinal";
  sinal.textContent = "%";
  porcento.append(valor, sinal);
  const pontos = document.createElement("span");
  pontos.className = "pontos";
  pontos.textContent = ponderado
    ? `${o.pontos} ${t("comum.pontos_e_votos", { n: o.votos })}`
    : t(o.votos === 1 ? "telao.um_voto" : "telao.n_votos", { n: o.votos });
  numeros.append(porcento, pontos);

  const trilho = document.createElement("div");
  trilho.className = "trilho";
  const preenchimento = document.createElement("div");
  preenchimento.className = "preenchimento";
  preenchimento.style.transitionDelay = `${0.45 + i * 0.12}s`;
  trilho.append(preenchimento);

  const legenda = document.createElement("small");
  legenda.className = "legenda-opcao";
  legenda.textContent = t("telao.preferencia");

  cartao.append(cabeca, rotulo, numeros, trilho, legenda);
  return cartao;
}

// Cada opção vira um cartão: a vencedora preenchida, as outras recuadas. Os cartões
// sobem em sequência, o número conta de zero e a barra enche logo atrás.
function mostrarResultado(opcoes) {
  const soma = opcoes.reduce((s, o) => s + o.pontos, 0) || 1;
  const ponderado = opcoes.some((o) => o.pontos !== o.votos);
  // empate não tem vencedora: só acende quando uma opção está sozinha na frente
  const maior = Math.max(...opcoes.map((o) => o.pontos));
  const vencedora = maior > 0 && opcoes.filter((o) => o.pontos === maior).length === 1
    ? opcoes.find((o) => o.pontos === maior) : null;

  const area = $("resultado");
  area.classList.toggle("muitas", opcoes.length > 3);
  area.replaceChildren(...opcoes.map((o, i) => cartaoDaOpcao(o, i, soma, vencedora, ponderado)));
  $("contagem").hidden = true;
  area.hidden = false;

  void area.offsetWidth; // aplica a largura 0 antes de mudar, para a transição acontecer
  opcoes.forEach((o, i) => {
    const cartao = area.children[i];
    cartao.querySelector(".preenchimento").style.width = `${(o.pontos / soma) * 100}%`;
    contar(cartao.querySelector(".valor"), Math.round((o.pontos / soma) * 100), 1400);
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
    if (m.cronometro) mostrarCronometro(m.cronometro);
    if (m.tipo === "cartao" || m.tipo === "snapshot") mostrarCartao(m.cartao);
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
