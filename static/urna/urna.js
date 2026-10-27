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
  $("tema").textContent = "Urna não configurada";
  throw new Error("urna sem configuração");
}
$("urna-id").textContent = URNA_ID;


// ---------- Tela ----------
let sessao = ler("sessao", null);
let ocupada = false;   // true durante confirmação ou mensagem de sucesso

// cada troca de tela entra com uma transição curta, em vez de um corte seco
function limpar() {
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
  if (cor) b.style.background = cor;
  if (classe) b.className = classe;
  b.onclick = aoClicar;
  // :active falha em algumas telas touch; pointerdown dá o retorno no instante do toque
  b.onpointerdown = () => b.classList.add("tocado");
  b.onpointerup = b.onpointercancel = b.onpointerleave = () => b.classList.remove("tocado");
  $("opcoes").appendChild(b);
}

function sinalizar(classe, duracao) {
  document.body.classList.add(classe);
  setTimeout(() => document.body.classList.remove(classe), duracao);
}

function renderizar() {
  if (ocupada) return;
  limpar();
  const questionario = sessao?.total_perguntas > 1;
  $("pergunta").hidden = !questionario || sessao.estado !== "ABERTA";
  if (questionario) $("pergunta").textContent = `Pergunta ${sessao.pergunta} de ${sessao.total_perguntas}`;
  if (!sessao || sessao.estado !== "ABERTA") {
    // entre perguntas do questionário a urna espera o mesário liberar a seguinte
    const entrePerguntas = questionario && (sessao.estado === "AGUARDANDO"
      ? sessao.pergunta > 1 : Boolean(sessao.proxima_pergunta));
    $("tema").textContent = entrePerguntas ? "Aguarde a próxima pergunta" : "Votação fechada";
    return;
  }
  $("tema").textContent = sessao.tema;
  for (const op of sessao.opcoes) {
    botao(op.rotulo, op.cor, () => confirmar(op));
  }
}


function confirmar(op) {
  ocupada = true;
  limpar();
  $("tema").textContent = `Confirmar voto em ${op.rotulo}?`;
  botao("Confirmar", op.cor, () => votar(op));
  botao("Corrigir", null, () => { ocupada = false; renderizar(); }, "secundario");
}

async function votar(op) {
  const voto = {
    id: crypto.randomUUID(),
    sessao_id: sessao.id,
    opcao: op.chave,
    votado_em: new Date().toISOString(),
  };
  gravar("fila", [...ler("fila", []), voto]);

  limpar();
  $("tema").textContent = "Enviando voto…";
  $("tema").classList.add("enviando");
  await enviarPendentes();

  // houve recusa: avisarRecusa() já assumiu a tela e ela fica até o "Entendi"
  if (document.body.classList.contains("recusa")) return;
  const naFila = ler("fila", []).some((v) => v.id === voto.id);
  limpar();
  if (naFila) {
    $("tema").textContent = "Sem conexão: voto guardado, será enviado quando a rede voltar";
  } else {
    $("tema").innerHTML = '<span class="carimbo">✓</span>Voto registrado';
    sinalizar("sucesso", 1500);
  }
  setTimeout(() => { ocupada = false; renderizar(); }, naFila ? 3000 : 1500);
}

const MENSAGENS_RECUSA = {
  sessao_encerrada: "Voto NÃO computado: a votação já foi encerrada",
  sessao_nao_aberta: "Voto NÃO computado: a votação ainda não foi aberta",
};

function avisarRecusa(motivo) {
  ocupada = true;
  limpar();
  document.body.classList.add("recusa");
  $("tema").textContent = `${MENSAGENS_RECUSA[motivo] ?? "Voto NÃO computado: o servidor recusou o voto"}. Chame o mesário.`;
  botao("Entendi", null, () => {
    document.body.classList.remove("recusa");
    ocupada = false;
    renderizar();
  }, "secundario");
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
      $("rede").textContent = "urna não autorizada";
      return;
    }
    atualizarSessao((await r.json()).sessao);
    $("rede").textContent = "online";
  } catch {
    $("rede").textContent = "offline";
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

$("urna-id").onclick = () => {
  const agora = Date.now();
  toques = [...toques.filter((t) => agora - t < 3000), agora];
  if (toques.length >= 5) {
    toques = [];
    $("exportar").hidden = !$("exportar").hidden;
    $("exportar").textContent = `exportar fila (${ler("fila", []).length})`;
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
  $("exportar").hidden = true;
};

// ---------- Início ----------
renderizar();
buscarSessao();
setInterval(buscarSessao, 5000);
cicloEnvio();