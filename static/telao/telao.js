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
  $("cartao-fonte").hidden = !cartao.fonte;
  $("cartao-fonte").textContent = cartao.fonte ? t("telao.fonte", { fonte: dominio(cartao.fonte) }) : "";
  ajustarCartao();
}

// O cartão era cortado em silêncio no 68vh: o texto acabava no meio de uma frase e
// ninguém no telão ficava sabendo. Agora a letra encolhe de 5% em 5% até caber. Só
// abaixo do piso o corte acontece, e aí o "…" diz que o texto continua.
const PISO_ESCALA = 0.6;

function ajustarCartao() {
  const cartao = $("cartao");
  if (cartao.hidden) return;
  let escala = 1;
  cartao.classList.remove("cortado");
  cartao.style.setProperty("--escala", escala);
  while (escala > PISO_ESCALA && cartao.scrollHeight > cartao.clientHeight) {
    escala -= 0.05;
    cartao.style.setProperty("--escala", escala.toFixed(2));
  }
  cartao.classList.toggle("cortado", cartao.scrollHeight > cartao.clientHeight);
}

addEventListener("resize", ajustarCartao);

let comQr = null;

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

// Um contexto só, criado ao abrir o telão e retomado no primeiro clique ou tecla da
// janela. Criado na hora do apito ele nasceria suspenso — sem erro nenhum, só sem
// som — e o telão é aberto por window.open, então nunca recebe um clique sozinho.
// Enquanto não estiver pronto, o cabeçalho pede o clique.
const som = new (window.AudioContext || window.webkitAudioContext)();

function mostrarBotaoDoSom() {
  $("ligar-som").hidden = som.state === "running";
}

function ligarSom() {
  som.resume().then(mostrarBotaoDoSom, () => {});
}

function apitar() {
  if (som.state !== "running") return; // sem o clique: o vermelho na tela já avisa
  try {
    const oscilador = som.createOscillator();
    const ganho = som.createGain();
    oscilador.frequency.value = 880;
    ganho.gain.setValueAtTime(0.25, som.currentTime);
    ganho.gain.exponentialRampToValueAtTime(0.001, som.currentTime + 0.7);
    oscilador.connect(ganho).connect(som.destination);
    oscilador.start();
    oscilador.stop(som.currentTime + 0.7);
  } catch {
    // navegador sem áudio: o vermelho na tela já avisa
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
  const mostrava = !$("faixa-teste").hidden;
  const mostrar = Boolean(m.sessao?.teste);
  $("faixa-teste").hidden = !mostrar;
  // a faixa de teste empurra o palco para baixo: o cartão refaz a conta da altura
  if (mostrava !== mostrar) ajustarCartao();
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
// Revelação: a apuração corre na tela. Os números sobem de zero, a largura de cada
// cartão acompanha a porcentagem e, quando a ordem muda, os cartões trocam de lugar.
// O selo da vencedora só entra no fim, para não entregar o resultado antes da hora.
const DURACAO_APURACAO = 6600;
// ritmos diferentes por posição: uma opção sobe mais cedo, outra vem de trás
const RITMOS = [1, 0.74, 1.26, 0.88, 1.12, 0.96];

function cartaoDaOpcao(o, i) {
  const cartao = document.createElement("article");
  cartao.className = "opcao";
  cartao.style.animationDelay = `${0.15 + i * 0.12}s`;
  cartao.style.flexGrow = 1;

  const cabeca = document.createElement("div");
  cabeca.className = "cabeca";
  const indice = document.createElement("span");
  indice.textContent = String(i + 1).padStart(2, "0");
  cabeca.append(indice);

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
  numeros.append(porcento, pontos);

  const trilho = document.createElement("div");
  trilho.className = "trilho";
  const preenchimento = document.createElement("div");
  preenchimento.className = "preenchimento";
  trilho.append(preenchimento);

  const legenda = document.createElement("small");
  legenda.className = "legenda-opcao";
  legenda.textContent = t("telao.preferencia");

  cartao.append(cabeca, rotulo, numeros, trilho, legenda);
  return cartao;
}

function textoDosPontos(o, votos, pontos, ponderado) {
  return ponderado
    ? `${pontos} ${t("comum.pontos_e_votos", { n: votos })}`
    : t(votos === 1 ? "telao.um_voto" : "telao.n_votos", { n: votos });
}

// desenha um instante da apuração: números, largura do cartão e barra
// Enquanto a apuração corre, nenhum cartão se acende: a cor da vencedora só entra
// quando o último voto aparece, em coroar().
function desenharParciais(cartoes, parciais, ponderado) {
  const soma = parciais.reduce((s, p) => s + p.pontos, 0) || 1;
  parciais.forEach((p, i) => {
    const fatia = p.pontos / soma;
    const cartao = cartoes[i];
    cartao.querySelector(".valor").textContent = Math.round(fatia * 100);
    cartao.querySelector(".pontos").textContent = textoDosPontos(p.opcao, p.votos, p.pontos, ponderado);
    cartao.querySelector(".preenchimento").style.width = `${fatia * 100}%`;
    // a divisória entre os cartões anda conforme a fatia; o mínimo da CSS segura o texto
    cartao.style.flexGrow = Math.max(fatia, 0.02).toFixed(3);
  });
}

function coroar(cartoes, opcoes, vencedora) {
  cartoes.forEach((cartao, i) => {
    const ganhou = opcoes[i] === vencedora;
    cartao.classList.toggle("vencedora", ganhou);
    cartao.classList.add("apurada");
    if (!ganhou) return;
    const selo = document.createElement("span");
    selo.className = "selo-vencedora";
    selo.textContent = t("telao.vencedora");
    cartao.querySelector(".cabeca").append(selo);
  });
}

// A cada quadro: números, largura e barra andam juntos, desacelerando no fim como
// uma apuração que fecha.
function correrApuracao(cartoes, opcoes, ponderado, aoTerminar) {
  const comeco = performance.now();
  const quadro = (agora) => {
    const t = Math.min(1, (agora - comeco) / DURACAO_APURACAO);
    const suave = 1 - (1 - t) ** 2.2;
    desenharParciais(cartoes, opcoes.map((o, i) => {
      const avanco = suave ** RITMOS[i % RITMOS.length];
      return { opcao: o, pontos: o.pontos * avanco, votos: Math.round(o.votos * avanco) };
    }), ponderado);
    if (t < 1) requestAnimationFrame(quadro);
    else aoTerminar();
  };
  requestAnimationFrame(quadro);
}

function mostrarResultado(opcoes) {
  const soma = opcoes.reduce((s, o) => s + o.pontos, 0) || 1;
  const ponderado = opcoes.some((o) => o.pontos !== o.votos);
  // empate não tem vencedora: só acende quando uma opção está sozinha na frente
  const maior = Math.max(...opcoes.map((o) => o.pontos));
  const vencedora = maior > 0 && opcoes.filter((o) => o.pontos === maior).length === 1
    ? opcoes.find((o) => o.pontos === maior) : null;

  const area = $("resultado");
  area.classList.toggle("muitas", opcoes.length > 3);
  const cartoes = opcoes.map((o, i) => cartaoDaOpcao(o, i));
  area.replaceChildren(...cartoes);
  $("contagem").hidden = true;
  area.hidden = false;

  const finais = opcoes.map((o) => ({ opcao: o, pontos: o.pontos, votos: o.votos }));
  const fechar = () => {
    desenharParciais(cartoes, finais, ponderado);
    coroar(cartoes, opcoes, vencedora);
  };
  if (semMovimento || maior === 0) {
    fechar();
    return;
  }
  desenharParciais(cartoes, opcoes.map((o) => ({ opcao: o, pontos: 0, votos: 0 })), ponderado);
  // a corrida começa depois que o último cartão terminou de subir
  setTimeout(() => correrApuracao(cartoes, opcoes, ponderado, fechar),
             900 + opcoes.length * 120);
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
    // o QR entrando ou saindo muda a largura do texto: o cartão refaz a conta
    if (comQr !== Boolean(codigo)) {
      comQr = Boolean(codigo);
      document.body.classList.toggle("com-qr", comQr);
      ajustarCartao();
    }
    if (codigo) {
      const link = `${location.origin}/celular/#s=${sessao_id}&c=${codigo}`;
      new QRCode(area, { text: link, width: 240, height: 240, correctLevel: QRCode.CorrectLevel.M });
    }
  } catch {
    // sem rede: mantém o último QR; o código antigo ainda vale por até 30s
  }
}

// Caindo a conexão, o telão congelava no último número e a sala achava que ninguém
// estava votando. A marca fica piscando até o WebSocket voltar.
function mostrarConexao(ligada) {
  $("sem-rede").hidden = ligada;
}

function conectar() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/telao`);
  ws.onopen = () => mostrarConexao(true);
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.cronometro) mostrarCronometro(m.cronometro);
    if (m.tipo === "cartao" || m.tipo === "snapshot") mostrarCartao(m.cartao);
    if (m.tipo === "snapshot" || m.tipo === "estado") mostrarEstado(m, m.tipo === "estado");
    if (m.tipo === "total" && sessaoAtual && m.sessao_id === sessaoAtual.id) {
      atualizarTotal(m.total);
    }
  };
  ws.onclose = () => {
    mostrarConexao(false);
    setTimeout(conectar, 2000);
  };
}

// Tela cheia: no projetor era F11 na mão, e o telão abre por window.open numa janela
// comum, com a barra do navegador à mostra.
function mostrarBotaoDaTela() {
  $("tela-cheia").textContent = t(document.fullscreenElement ? "telao.sair_tela_cheia" : "telao.tela_cheia");
}

$("tela-cheia").onclick = () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen().catch(() => {});
};
addEventListener("fullscreenchange", mostrarBotaoDaTela);

som.onstatechange = mostrarBotaoDoSom;
addEventListener("pointerdown", ligarSom);
addEventListener("keydown", ligarSom);
$("ligar-som").onclick = ligarSom;
mostrarBotaoDoSom();

conectar();
atualizarQr();
// o código muda a cada 30s; buscar a cada 5s mantém o QR sempre na janela atual
setInterval(atualizarQr, 5000);
