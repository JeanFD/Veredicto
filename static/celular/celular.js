const $ = (id) => document.getElementById(id);
const ler = (chave, padrao) => JSON.parse(localStorage.getItem(chave)) ?? padrao;
const gravar = (chave, valor) => localStorage.setItem(chave, JSON.stringify(valor));

// O QR do telão traz a sessão e um código que vale por ~30s (#s=1&c=...).
// O código é trocado uma vez por uma cédula, guardada aqui: ela vale um voto na sessão.
const hash = new URLSearchParams(location.hash.slice(1));
history.replaceState(null, "", location.pathname);
// novo QR escaneado com a página já aberta só muda o #: recarrega para ler o código novo
addEventListener("hashchange", () => location.reload());
let sessaoId = Number(hash.get("s")) || ler("ultima_sessao", null);
const codigo = hash.get("c");

const cedulas = () => ler("cedulas", {});
const minhaCedula = () => cedulas()[sessaoId];
const guardarCedula = (dados) => gravar("cedulas", { ...cedulas(), [sessaoId]: { ...minhaCedula(), ...dados } });

// ---------- Tela ----------
function tela(texto, classe) {
  $("opcoes").innerHTML = "";
  $("pergunta").hidden = true;
  $("tema").textContent = texto;
  document.body.className = classe ?? "";
  const main = document.querySelector("main");
  main.classList.remove("entrando");
  void main.offsetWidth;
  main.classList.add("entrando");
}

function botao(texto, cor, aoClicar, classe) {
  const b = document.createElement("button");
  b.textContent = texto;
  if (cor) b.style.background = cor;
  if (classe) b.className = classe;
  b.onclick = aoClicar;
  b.onpointerdown = () => b.classList.add("tocado");
  b.onpointerup = b.onpointercancel = b.onpointerleave = () => b.classList.remove("tocado");
  $("opcoes").appendChild(b);
}

const MOTIVOS = ["codigo_expirado", "sessao_fechada", "sessao_inexistente", "cedula_invalida", "ja_votou", "cedula_usada",
  "celular_desligado"];
const mensagem = (motivo, padrao) => (MOTIVOS.includes(motivo) ? t(`celular.motivo.${motivo}`) : t(padrao));

async function enviar(caminho, corpo) {
  const r = await fetch(caminho, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
    signal: AbortSignal.timeout(10000),
  });
  const dados = await r.json().catch(() => ({}));
  return { ok: r.ok, motivo: dados.detail?.motivo, dados };
}

// ---------- Fluxo ----------
async function iniciar() {
  if (!sessaoId) return tela(t("celular.escaneie"));
  gravar("ultima_sessao", sessaoId);
  if (minhaCedula()?.votou) {
    tela(mensagem("ja_votou"), "sucesso");
    return aguardarProxima();
  }

  let sessao;
  try {
    if (!minhaCedula()?.cedula) {
      if (!codigo) return tela(t("celular.escaneie"));
      const r = await enviar("/api/celular/entrar", { sessao_id: sessaoId, codigo });
      if (!r.ok) return tela(mensagem(r.motivo, "celular.nao_entrou"));
      sessao = r.dados.sessao;
      guardarCedula({ cedula: r.dados.cedula, grupo_id: sessao.grupo_id, pergunta: sessao.pergunta });
    } else {
      sessao = (await (await fetch("/api/sessao/ativa")).json()).sessao;
    }
  } catch {
    return semConexao(iniciar);
  }
  $("faixa-teste").hidden = !sessao?.teste;
  if (sessao?.id === sessaoId && !sessao.celular) return tela(mensagem("celular_desligado"));
  if (!sessao || sessao.id !== sessaoId || sessao.estado !== "ABERTA") {
    tela(mensagem("sessao_fechada"));
    return aguardarProxima();
  }
  escolher(sessao);
}

function escolher(sessao) {
  tela(sessao.tema);
  if (sessao.total_perguntas > 1) {
    $("pergunta").textContent = t("comum.pergunta_de", { n: sessao.pergunta, total: sessao.total_perguntas });
    $("pergunta").hidden = false;
  }
  for (const op of sessao.opcoes) botao(op.rotulo, op.cor, () => confirmar(sessao, op));
}

function confirmar(sessao, op) {
  tela(t("comum.confirmar_voto", { opcao: op.rotulo }));
  botao(t("comum.confirmar"), op.cor, () => votar(op));
  botao(t("comum.corrigir"), null, () => escolher(sessao), "secundario");
}

async function votar(op) {
  // o id do voto é guardado antes do envio: um reenvio após queda de rede não duplica
  if (!minhaCedula().voto_id) guardarCedula({ voto_id: crypto.randomUUID() });
  tela(t("comum.enviando"));
  $("tema").classList.add("enviando");
  let r;
  try {
    r = await enviar("/api/celular/votar", { cedula: minhaCedula().cedula, id: minhaCedula().voto_id, opcao: op.chave });
  } catch {
    return semConexao(() => votar(op));
  }
  if (r.ok || r.motivo === "ja_votou") {
    guardarCedula({ votou: true });
    tela("");
    $("tema").innerHTML = '<span class="carimbo">✓</span>';
    $("tema").append(t("comum.voto_registrado"));
    document.body.className = "sucesso";
    return aguardarProxima();
  }
  if (r.motivo === "sessao_fechada") return tela(t("celular.encerrada"), "recusa");
  if (r.motivo === "celular_desligado") return tela(mensagem(r.motivo), "recusa");
  tela(mensagem(r.motivo, "celular.nao_computado"), "recusa");
}

// Questionário: quando o mesário libera a pergunta seguinte, o celular troca a
// cédula atual pela da nova pergunta, sem precisar escanear o QR de novo.
let esperando = null;

function aguardarProxima() {
  const minha = minhaCedula();
  if (!minha?.grupo_id || esperando) return;
  esperando = setInterval(async () => {
    let ativa;
    try {
      ativa = (await (await fetch("/api/sessao/ativa")).json()).sessao;
    } catch {
      return; // sem rede: tenta na próxima volta
    }
    if (!ativa || ativa.grupo_id !== minha.grupo_id || ativa.pergunta <= minha.pergunta
        || ativa.estado !== "ABERTA") return;
    clearInterval(esperando);
    esperando = null;
    let r;
    try {
      r = await enviar("/api/celular/proxima", { cedula: minha.cedula });
    } catch {
      return semConexao(aguardarProxima);
    }
    if (!r.ok) return tela(mensagem(r.motivo, "celular.motivo.cedula_usada"));
    sessaoId = ativa.id;
    gravar("ultima_sessao", sessaoId);
    guardarCedula({ cedula: r.dados.cedula, grupo_id: ativa.grupo_id, pergunta: ativa.pergunta });
    escolher(r.dados.sessao);
  }, 3000);
}

function semConexao(tentarDeNovo) {
  tela(t("celular.sem_conexao"), "recusa");
  botao(t("celular.tentar_de_novo"), null, tentarDeNovo, "secundario");
}

iniciar();
