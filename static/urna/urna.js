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

function limpar() {
  $("opcoes").innerHTML = "";
}

function botao(texto, cor, aoClicar, classe) {
  const b = document.createElement("button");
  b.textContent = texto;
  if (cor) b.style.background = cor;
  if (classe) b.className = classe;
  b.onclick = aoClicar;
  $("opcoes").appendChild(b);
}


if (ocupada) return;
  limpar();
  if (!sessao || sessao.estado !== "ABERTA") {
    $("tema").textContent = "Votação fechada";
    return;
  }
  $("tema").textContent = sessao.tema;
  for (const op of sessao.opcoes) {
    botao(op.rotulo, op.cor, () => confirmar(op));
  }


function confirmar(op) {
  ocupada = true;
  limpar();
  $("tema").textContent = `Confirmar voto em ${op.rotulo}?`;
  botao("Confirmar", op.cor, () => votar(op));
  botao("Corrigir", null, () => { ocupada = false; renderizar(); }, "secundario");
}

function votar(op) {
  const fila = ler("fila", []);
  fila.push({
    id: crypto.randomUUID(),
    sessao_id: sessao.id,
    opcao: op.chave,
    votado_em: new Date().toISOString(),
  });
  gravar("fila", fila);

  limpar();
  $("tema").textContent = "Voto registrado ✓";
  setTimeout(() => { ocupada = false; renderizar(); }, 1500);
  enviarPendentes();
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
    const r = await fetch("/api/sessao/ativa");
    atualizarSessao((await r.json()).sessao);
    $("rede").textContent = "online";
  } catch {
    $("rede").textContent = "offline";
  }
}

// ---------- Envio ----------
let espera = 1000;
let enviando = false;

async function enviarPendentes() {
  if (enviando) return;
  enviando = true;
  try {
    for (const voto of ler("fila", [])) {
      const r = await fetch("/api/votos", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Urna-Token": TOKEN },
        body: JSON.stringify(voto),
      });
      if (r.status >= 500 || r.status === 401) throw new Error(`HTTP ${r.status}`);
      if (!r.ok) gravar("recusados", [...ler("recusados", []), { ...voto, status: r.status }]);
      gravar("fila", ler("fila", []).filter((v) => v.id !== voto.id));
    }
    espera = 1000;
  } catch {
    espera = Math.min(espera * 2, 30000);
  } finally {
    enviando = false;
  }
}

async function cicloEnvio() {
  await enviarPendentes();
  setTimeout(cicloEnvio, espera);
}

// ---------- Início ----------
renderizar();
buscarSessao();
setInterval(buscarSessao, 5000);
cicloEnvio();