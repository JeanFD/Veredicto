(() => {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("id") && p.get("token")) {
    localStorage.setItem("urna_id", p.get("id"));
    localStorage.setItem("urna_token", p.get("token"));
    history.replaceState(null, "", location.pathname);
  }
})();

const URNA_ID = localStorage.getItem("urna_id");
const TOKEN = localStorage.getItem("urna_token");
const $ = (id) => document.getElementById(id);
const ler = (chave, padrao) => JSON.parse(localStorage.getItem(chave)) ?? padrao;
const gravar = (chave, valor) => localStorage.setItem(chave, JSON.stringify(valor));

if (!URNA_ID || !TOKEN) {
  parear();
  throw new Error("urna sem configuração");
}
$("urna-id").textContent = URNA_ID;


// ---------- Tela ----------
let sessao = ler("sessao", null);
let ocupada = false;   // true durante confirmação ou mensagem de sucesso

// cada troca de tela entra com uma transição curta, em vez de um corte seco
function limpar() {
  pararEspera();
  avisar(null);
  $("opcoes").innerHTML = "";
  $("tema").classList.remove("enviando");
  const tela = document.querySelector("main");
  tela.classList.remove("entrando");
  void tela.offsetWidth; // reinicia a animação
  tela.classList.add("entrando");
}

function botao(texto, cor, aoClicar, classe) {
  const b = document.createElement("button");
  b.textContent = texto;
  if (cor) {
    b.style.background = cor;
    // a cor vem de um seletor livre: o texto acompanha para continuar legível
    b.style.color = corDoTexto(cor);
  }
  if (classe) b.className = classe;
  b.onclick = aoClicar;
  // :active falha em algumas telas touch; pointerdown dá o retorno no instante do toque
  b.onpointerdown = () => b.classList.add("tocado");
  b.onpointerup = b.onpointercancel = b.onpointerleave = () => b.classList.remove("tocado");
  $("opcoes").appendChild(b);
  return b;
}

function avisar(texto) {
  $("aviso").hidden = !texto;
  $("aviso").textContent = texto ?? "";
}

function sinalizar(classe, duracao) {
  document.body.classList.add(classe);
  setTimeout(() => document.body.classList.remove(classe), duracao);
}

function renderizar() {
  $("faixa-teste").hidden = !sessao?.teste;
  if (ocupada) return;
  limpar();
  const questionario = sessao?.total_perguntas > 1;
  $("pergunta").hidden = !questionario || sessao.estado !== "ABERTA";
  if (questionario) $("pergunta").textContent = t("comum.pergunta_de", { n: sessao.pergunta, total: sessao.total_perguntas });
  if (!sessao || sessao.estado !== "ABERTA") {
    // entre perguntas do questionário a urna espera o mesário liberar a seguinte
    const entrePerguntas = questionario && (sessao.estado === "AGUARDANDO"
      ? sessao.pergunta > 1 : Boolean(sessao.proxima_pergunta));
    $("tema").textContent = t(entrePerguntas ? "urna.aguarde_proxima" : "urna.fechada");
    return;
  }
  $("tema").textContent = sessao.tema;
  for (const op of sessao.opcoes) {
    botao(op.rotulo, op.cor, () => confirmar(op));
  }
}


// A cédula não fica armada esperando: se o eleitor se afastar, ela volta sozinha, para
// que o próximo não encontre o voto de outra pessoa pronto para confirmar. E o
// "Confirmar" nasce no lugar da opção recém-tocada: um toque duplo escolheria e
// votaria. Por isso os botões da confirmação só aparecem passada a espera — e, à
// vista, já funcionam. Antes o botão aparecia desativado, parecia pronto, e o
// toque de quem confirmava rápido sumia sem aviso.
// confirmacao: segundos até a cédula voltar sozinha; avisar: segundos finais contados
// na tela; espera: ms até os botões da confirmação aparecerem. Os testes de ponta a
// ponta encurtam os dois primeiros por window.TEMPOS_URNA, que em produção não existe.
const TEMPOS = { confirmacao: 30, avisar: 10, espera: 500, ...(window.TEMPOS_URNA ?? {}) };

let esperaConfirmacao = null;
let mostrarBotoes = null;

function pararEspera() {
  clearInterval(esperaConfirmacao);
  clearTimeout(mostrarBotoes);
  esperaConfirmacao = null;
  $("opcoes").classList.remove("esperando", "surgindo");
}

function voltarParaCedula() {
  ocupada = false;
  renderizar();
}

function contarParaVoltar() {
  let faltam = TEMPOS.confirmacao;
  esperaConfirmacao = setInterval(() => {
    faltam -= 1;
    if (faltam <= 0) return voltarParaCedula();
    if (faltam <= TEMPOS.avisar) avisar(t("urna.volta_em", { s: faltam }));
  }, 1000);
}

function confirmar(op) {
  ocupada = true;
  limpar();
  $("tema").textContent = t("comum.confirmar_voto", { opcao: op.rotulo });
  // os botões já ocupam o lugar (a pergunta não pula quando eles surgem), mas
  // invisíveis não recebem toque: o segundo toque de um toque duplo cai no fundo
  $("opcoes").classList.add("esperando");
  botao(t("comum.confirmar"), op.cor, () => votar(op));
  botao(t("comum.corrigir"), null, voltarParaCedula, "secundario");
  mostrarBotoes = setTimeout(() => {
    $("opcoes").classList.remove("esperando", "surgindo");
    $("opcoes").classList.add("surgindo");
  }, TEMPOS.espera);
  contarParaVoltar();
}

async function votar(op) {
  Sons.preparar(); // ainda dentro do toque no "Confirmar": depois do envio já não vale
  const voto = {
    id: crypto.randomUUID(),
    sessao_id: sessao.id,
    opcao: op.chave,
    votado_em: new Date().toISOString(),
  };
  gravar("fila", [...ler("fila", []), voto]);

  limpar();
  $("tema").textContent = t("comum.enviando");
  $("tema").classList.add("enviando");
  await enviarPendentes();

  // houve recusa: avisarRecusa() já assumiu a tela e ela fica até o "Entendi"
  if (document.body.classList.contains("recusa")) return;
  const naFila = ler("fila", []).some((v) => v.id === voto.id);
  limpar();
  if (naFila) {
    $("tema").textContent = t("urna.sem_conexao");
  } else {
    $("tema").innerHTML = '<span class="carimbo">✓</span>';
    $("tema").append(t("comum.voto_registrado"));
    sinalizar("sucesso", 1500);
    Sons.voto();
  }
  setTimeout(() => { ocupada = false; renderizar(); }, naFila ? 3000 : 1500);
}

function avisarRecusa(motivo) {
  ocupada = true;
  limpar();
  document.body.classList.add("recusa");
  const conhecido = ["sessao_encerrada", "sessao_nao_aberta"].includes(motivo);
  $("tema").textContent = t("urna.chame_mesario", { motivo: t(conhecido ? `urna.recusa.${motivo}` : "urna.recusa.outra") });
  botao(t("urna.entendi"), null, () => {
    document.body.classList.remove("recusa");
    ocupada = false;
    renderizar();
  }, "secundario");
}

// ---------- Sem autorização ----------
// Token reemitido, banco restaurado: o servidor passa a recusar a urna. Antes a tela
// seguia mostrando a pergunta guardada e o eleitor votava no vazio. Agora ela assume
// a tela e oferece o repareamento, atrás de uma segunda confirmação — desconfigurar
// uma urna no meio da votação custa caro.
let semAutorizacao = false;

function mostrarSemAutorizacao() {
  ocupada = true;
  limpar();
  document.body.classList.add("sem-autorizacao");
  $("pergunta").hidden = true;
  $("tema").textContent = t("urna.sem_autorizacao");
  avisar(t("urna.sem_autorizacao_ajuda"));
  botao(t("urna.parear_de_novo"), null, pedirRepareamento, "secundario");
}

function pedirRepareamento() {
  limpar();
  $("tema").textContent = t("urna.confirmar_repareamento");
  const presos = ler("fila", []).length;
  if (presos) avisar(t("urna.repareamento_fila", { n: presos }));
  botao(t("urna.desconfigurar"), "#b42318", () => {
    localStorage.removeItem("urna_id");
    localStorage.removeItem("urna_token");
    location.reload();
  });
  botao(t("urna.cancelar"), null, mostrarSemAutorizacao, "secundario");
}

// ---------- Sessão ----------
function atualizarSessao(nova) {
  const mudou = JSON.stringify(nova) !== JSON.stringify(sessao);
  sessao = nova;
  gravar("sessao", nova);
  if (mudou) renderizar();
}

async function buscarSessao() {
  try {
    const r = await fetch("/api/urnas/heartbeat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Urna-Token": TOKEN },
      body: JSON.stringify({ pendentes: ler("fila", []).length, recusados: ler("recusados", []).length }),
    });
    if (r.status === 401) {
      $("rede").textContent = t("urna.nao_autorizada");
      if (!semAutorizacao) {
        semAutorizacao = true;
        mostrarSemAutorizacao();
      }
      return;
    }
    const corpo = await r.json();
    if (semAutorizacao) {
      // autorizada de novo: sai da tela de aviso mesmo que a sessão não tenha mudado
      semAutorizacao = false;
      ocupada = false;
      sessao = null;
      document.body.classList.remove("sem-autorizacao");
    }
    atualizarSessao(corpo.sessao);
    $("rede").textContent = t("urna.online");
  } catch {
    $("rede").textContent = t("urna.offline");
  }
}

// ---------- Envio ----------
let espera = 1000;
let envio = null;

// Quem chama durante um envio em andamento espera o mesmo envio,
// que relê a fila a cada voto e assim também leva os votos novos.
function enviarPendentes() {
  envio ??= esvaziarFila().finally(() => { envio = null; });
  return envio;
}

async function esvaziarFila() {
  try {
    let voto;
    while ((voto = ler("fila", [])[0])) {
      const r = await fetch("/api/votos", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Urna-Token": TOKEN },
        body: JSON.stringify(voto),
        signal: AbortSignal.timeout(8000),
      });
      if (r.status >= 500 || r.status === 401) throw new Error(`HTTP ${r.status}`);
      if (!r.ok) {
        const motivo = (await r.json().catch(() => ({}))).detail?.motivo;
        gravar("recusados", [...ler("recusados", []), { ...voto, status: r.status, motivo }]);
        avisarRecusa(motivo);
      }
      gravar("fila", ler("fila", []).filter((v) => v.id !== voto.id));
    }
    espera = 1000;
  } catch {
    espera = Math.min(espera * 2, 30000);
  }
}

async function cicloEnvio() {
  await enviarPendentes();
  setTimeout(cicloEnvio, espera);
}

// ---------- Exportar fila (mesário) ----------
// O arquivo traz votos ainda não enviados: o botão fica escondido do eleitor
// e aparece com 5 toques rápidos no id da urna, no rodapé.
let toques = [];

// O mesmo gesto traz o seletor de idioma: configurar a urna é tarefa de quem monta a
// sala. Solto no canto da tela, ele virava a cédula inteira para inglês com um toque.
function alternarControlesDoMesario() {
  const mostrar = $("exportar").hidden;
  $("exportar").hidden = !mostrar;
  $("exportar").textContent = t("urna.exportar", { n: ler("fila", []).length });
  if (!mostrar) return $("idioma")?.remove();
  if (!$("idioma")) seletorIdioma(document.querySelector("footer"));
}

$("urna-id").onclick = () => {
  const agora = Date.now();
  toques = [...toques.filter((t) => agora - t < 3000), agora];
  if (toques.length >= 5) {
    toques = [];
    alternarControlesDoMesario();
  }
};

$("exportar").onclick = () => {
  const fila = ler("fila", []);
  const conteudo = {
    formato: "veredicto-fila",
    versao: 1,
    urna_id: URNA_ID,
    exportado_em: new Date().toISOString(),
    votos: fila,
  };
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(conteudo, null, 2)], { type: "application/json" }));
  link.download = `fila-${URNA_ID}-${conteudo.exportado_em.replace(/[:.]/g, "-")}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
  // a fila continua na urna: reimportar ou reenviar não duplica (id por voto)
  alternarControlesDoMesario();
};

// ---------- Início ----------
// abre mesmo recarregada sem rede: ver a estratégia de atualização em sw.js
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/urna/sw.js", { scope: "/urna/" }).catch(() => {});
}
renderizar();
buscarSessao();
setInterval(buscarSessao, 5000);
cicloEnvio();

Sons.prepararNoToque();
