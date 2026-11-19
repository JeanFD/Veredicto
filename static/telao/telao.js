const $ = (id) => document.getElementById(id);
const semMovimento = matchMedia("(prefers-reduced-motion: reduce)").matches;
let sessaoAtual = null;

// ---------- Aparência ----------
// O admin troca cores, textos e o jeito da revelação no painel (app/aparencia.py);
// chega no snapshot e de novo, na hora, quando ele salva. Texto em branco fica com
// a tradução da tela; texto escrito vale para os dois idiomas.
let aparencia = {
  cores: {}, textos: {},
  revelacao: { regressiva: true, apuracao: true, duracao: 6.6, mostrar_votos: true },
};
const TEXTOS_PERSONALIZAVEIS = {
  aguardando: "telao.aguardando",
  votos: "telao.legenda.ABERTA",
  vencedora: "telao.vencedora",
  preferencia: "telao.preferencia",
  celular: "telao.vote_celular",
};

function texto(chave) {
  const nome = Object.keys(TEXTOS_PERSONALIZAVEIS).find((n) => TEXTOS_PERSONALIZAVEIS[n] === chave);
  return (nome && aparencia.textos[nome]) || t(chave);
}

function aplicarAparencia(a) {
  if (!a) return;
  aparencia = a;
  const raiz = document.documentElement.style;
  const { fundo, cartao, destaque, texto: corTexto } = a.cores;
  raiz.setProperty("--preto", fundo);
  raiz.setProperty("--carvao", cartao);
  raiz.setProperty("--limao", destaque);
  raiz.setProperty("--texto", corTexto);
  // o que vai em cima do destaque (vencedora, selo): o fundo, ou o texto se o fundo
  // não aparecer nele — um destaque escuro com fundo preto apagaria a vencedora
  raiz.setProperty("--sobre-destaque", maisLegivel(destaque, [fundo, corTexto]));
  document.body.classList.toggle("sem-votos", !a.revelacao.mostrar_votos);
  // o que já está na tela troca sem esperar a próxima mudança de estado
  $("texto-celular").textContent = texto("telao.vote_celular");
  if (!sessaoAtual) $("tema").textContent = texto("telao.aguardando");
  if (sessaoAtual?.estado === "ABERTA") $("legenda").textContent = texto("telao.legenda.ABERTA");
  document.querySelectorAll(".selo-vencedora").forEach((el) => { el.textContent = texto("telao.vencedora"); });
  document.querySelectorAll(".legenda-opcao").forEach((el) => { el.textContent = texto("telao.preferencia"); });
}

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

// A situação fica na pílula do cabeçalho e o total no rodapé, sempre à vista.
function mostrarMoldura(m) {
  const estado = m.sessao?.estado;
  $("situacao").textContent = t(`telao.situacao.${estado ?? "AGUARDANDO"}`);
  $("situacao").classList.toggle("apurado", estado === "REVELADA");
  mostrarTotalDoRodape(m.total ?? 0, m.resultado);
  mostrarContextoDoRodape();
}

// A situação já está na pílula do cabeçalho e o caso no alto do palco, inclusive com
// um cartão na tela: repetir os dois no rodapé só enchia o telão. O tema é o único
// que o cartão cobre, então é o único que o rodapé precisa resgatar.
function mostrarContextoDoRodape() {
  const comCartao = document.body.classList.contains("com-cartao");
  $("rodape-tema").textContent = comCartao ? sessaoAtual?.tema ?? "" : "";
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
  mostrarContextoDoRodape();
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

// Um contexto só (em /sons.js), criado ao abrir o telão e retomado no primeiro
// clique ou tecla da janela. Criado na hora do apito ele nasceria suspenso — sem
// erro nenhum, só sem som — e o telão é aberto por window.open, então nunca recebe
// um clique sozinho. Enquanto não estiver pronto, o cabeçalho pede o clique.
const som = Sons.obter();

function mostrarBotaoDoSom() {
  $("ligar-som").hidden = !som || !Sons.ligado || som.state === "running";
}

// só o resume(): o destrave do Sons.preparar() toca um buffer dentro do clique, e
// no Chromium isso tirava do botão de tela cheia o gesto de que ele precisa
function ligarSom() {
  if (som) som.resume().then(mostrarBotaoDoSom, () => {});
}

// tiques nos últimos segundos: um por segundo inteiro, só enquanto corre
const TIQUES_FINAIS = 5;
let ultimoTique = null;
let menorTique = Infinity;

function mostrarCronometro(c) {
  if (c.visivel && c.rodando && !(cronometro?.visivel && cronometro?.rodando)) Sons.cronometroInicio();
  cronometro = { ...c, recebido: performance.now() };
  desenharCronometro();
  clearInterval(tiqueCronometro);
  if (c.visivel && c.rodando) tiqueCronometro = setInterval(desenharCronometro, 200);
}

function desenharCronometro() {
  const c = cronometro;
  $("cronometro").hidden = !c.visivel;
  if (!c.visivel) {
    apitou = false;
    menorTique = Infinity;
    return;
  }
  const restante = c.rodando ? c.restante - (performance.now() - c.recebido) / 1000 : c.restante;
  const esgotado = restante < 0;
  $("cronometro-titulo").textContent = c.titulo;
  $("cronometro-tempo").textContent = (esgotado ? "+" : "") + formatarTempo(restante);
  $("cronometro").classList.toggle("esgotado", esgotado);
  $("cronometro-esgotado").hidden = !esgotado;
  // O servidor reenvia o cronômetro a cada poucos segundos, e o relógio dele e o
  // daqui não batem no décimo: logo depois do zero, uma mensagem com 0,2 s de
  // sobra desfazia o "esgotado" e o apito tocava de novo. Apito e tiques só se
  // rearmam quando o tempo volta de verdade (nova fala, +1 min) ou sai da tela.
  if (restante > 1) apitou = false;
  if (restante > TIQUES_FINAIS + 1 || !c.rodando) menorTique = Infinity;
  if (esgotado && !apitou) {
    Sons.cronometroFim();
    apitou = true;
  }
  // tica ao virar cada um dos últimos segundos, uma vez cada; um telão que abre no
  // meio da contagem espera a próxima virada, sem tique solto
  const segundo = c.rodando && !esgotado ? Math.ceil(restante) : null;
  if (segundo !== null && segundo <= TIQUES_FINAIS && ultimoTique !== null
      && segundo < ultimoTique && segundo < menorTique) {
    Sons.cronometroTique();
    menorTique = segundo;
  }
  ultimoTique = segundo;
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
  $("tema").textContent = m.sessao ? m.sessao.tema : texto("telao.aguardando");
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
    if (revelandoAgora) regressiva(() => mostrarResultado(m.resultado, true));
    else mostrarResultado(m.resultado);
    return;
  }
  // revelada, o resultado fala por si: sem legenda
  const comLegenda = m.sessao && m.sessao.estado !== "REVELADA";
  $("legenda").textContent = comLegenda ? texto(`telao.legenda.${m.sessao.estado}`) : "";
  atualizarTotal(m.total);
  $("resultado").hidden = true;
  $("contagem").hidden = false;
}

// 3·2·1 com um segundo por número, no ritmo de quem conta em voz alta: em meio
// segundo a sala não acompanhava e a contagem parecia um piscar
function regressiva(depois) {
  if (semMovimento || !aparencia.revelacao.regressiva) return depois();
  const tela = $("regressiva");
  // o som sai no tique e a tela espera o atraso da caixa de som: no projetor, o
  // bipe chegava depois do número
  const atraso = Sons.latencia() * 1000;
  const naTela = (desenhar) => setTimeout(desenhar, atraso);
  naTela(() => { tela.hidden = false; });
  let n = 3;
  const tique = () => {
    if (n === 0) {
      naTela(() => {
        tela.hidden = true;
        depois();
      });
      return;
    }
    const valor = n--;
    Sons.regressiva(valor);
    naTela(() => {
      const numero = document.createElement("span");
      numero.textContent = valor;
      tela.replaceChildren(numero);
    });
    setTimeout(tique, 1000);
  };
  tique();
}

// Com pesos diferentes, as barras e o vencedor seguem os pontos (soma dos pesos), e
// cada opção mostra também quantas pessoas votaram; com todos os pesos 1, são iguais.
// Revelação: a apuração corre na tela. Os números sobem de zero, a largura de cada
// cartão acompanha a porcentagem e, quando a ordem muda, os cartões trocam de lugar.
// O selo da vencedora só entra no fim, para não entregar o resultado antes da hora.
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
  legenda.textContent = texto("telao.preferencia");

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
    selo.textContent = texto("telao.vencedora");
    cartao.querySelector(".cabeca").append(selo);
  });
}

// A cada quadro: números, largura e barra andam juntos, desacelerando no fim como
// uma apuração que fecha.
function correrApuracao(cartoes, opcoes, ponderado, aoTerminar) {
  const comeco = performance.now();
  let proximoTique = 0;
  const quadro = (agora) => {
    const t = Math.min(1, (agora - comeco) / (aparencia.revelacao.duracao * 1000));
    // os tiques vão espaçando junto com a desaceleração da apuração
    if (t < 1 && agora >= proximoTique) {
      Sons.apuracao(t);
      proximoTique = agora + 70 + t * 230;
    }
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

function mostrarResultado(opcoes, aoVivo = false) {
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
  const fechar = (comSom) => {
    desenharParciais(cartoes, finais, ponderado);
    coroar(cartoes, opcoes, vencedora);
    if (comSom) vencedora ? Sons.vencedora() : Sons.empate();
  };
  // sem animação, a revelação ao vivo ainda toca o fecho; um telão que abre já com
  // o resultado na tela não toca nada
  if (semMovimento || maior === 0 || !aparencia.revelacao.apuracao) {
    fechar(aoVivo && maior > 0);
    return;
  }
  desenharParciais(cartoes, opcoes.map((o) => ({ opcao: o, pontos: 0, votos: 0 })), ponderado);
  // a corrida começa depois que o último cartão terminou de subir
  setTimeout(() => correrApuracao(cartoes, opcoes, ponderado, () => fechar(true)),
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
    if (m.aparencia) aplicarAparencia(m.aparencia);
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

if (som) som.onstatechange = mostrarBotaoDoSom;
addEventListener("pointerdown", ligarSom);
addEventListener("keydown", ligarSom);
$("ligar-som").onclick = ligarSom;
mostrarBotaoDoSom();

conectar();
atualizarQr();
// o código muda a cada 30s; buscar a cada 5s mantém o QR sempre na janela atual
setInterval(atualizarQr, 5000);
