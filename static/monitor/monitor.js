const $ = (id) => document.getElementById(id);
let senha = sessionStorage.getItem("senha");

async function buscar() {
  const r = await fetch("/api/admin/metricas", { headers: { Authorization: "Basic " + btoa("mesario:" + senha) } });
  if (r.status === 401) throw new Error("senha");
  return r.json();
}

function linha(rotulo, valor) {
  const tr = document.createElement("tr");
  for (const texto of [rotulo, valor]) {
    const td = document.createElement("td");
    td.textContent = texto;
    tr.appendChild(td);
  }
  return tr;
}

function mostrar(m) {
  const vpm = m.votos_por_minuto;
  // o minuto atual ainda está em andamento: o "último minuto" é o anterior completo
  $("vpm").textContent = vpm.at(-2);
  $("vpm-agora").textContent = t("monitor.vpm_agora", { n: vpm.at(-1) });
  $("urnas").textContent = `${m.urnas.online} / ${m.urnas.ativas}`;
  $("cartao-urnas").classList.toggle("alerta", m.urnas.online < m.urnas.ativas);
  const { p50, p95 } = m.latencia_ms;
  $("latencia").textContent = p50 === null ? "—" : `${Math.round(p50)} · ${Math.round(p95)} ms`;
  $("sessao").textContent = m.sessao ? `${m.sessao.tema} · ${t(`estado.${m.sessao.estado}`)}` : t("monitor.nenhuma_sessao");
  $("total").textContent = m.sessao ? t("monitor.n_votos", { n: m.sessao.total }) : "—";

  const maximo = Math.max(1, ...vpm);
  $("grafico").replaceChildren(...vpm.map((n, i) => {
    const barra = document.createElement("div");
    barra.style.height = `${(n / maximo) * 100}%`;
    barra.title = i === vpm.length - 1 ? t("monitor.barra_atual", { n }) : t("monitor.barra_ha", { n, min: vpm.length - 1 - i });
    return barra;
  }));

  $("totais").replaceChildren(
    ...Object.entries(m.votos_total).map(([origem, n]) => linha(t("monitor.aceitos", { origem }), n)),
    ...Object.entries(m.recusados_total).map(([motivo, n]) => linha(t("monitor.recusados", { motivo }), n)),
  );
  if (!$("totais").children.length) $("totais").appendChild(linha(t("monitor.nenhum_voto"), ""));
  $("atualizado").textContent = t("monitor.atualizado", { hora: new Date().toLocaleTimeString(document.documentElement.lang) });
}

async function atualizar() {
  try {
    mostrar(await buscar());
  } catch (e) {
    if (e.message === "senha") return sair();
    $("atualizado").textContent = t("monitor.sem_conexao", { hora: new Date().toLocaleTimeString(document.documentElement.lang) });
  }
}

function sair() {
  sessionStorage.removeItem("senha");
  location.reload();
}

function iniciar() {
  $("login").hidden = true;
  $("painel").hidden = false;
  atualizar();
  setInterval(atualizar, 5000);
}

$("form-login").onsubmit = async (e) => {
  e.preventDefault();
  senha = $("senha").value;
  try {
    await buscar();
    sessionStorage.setItem("senha", senha);
    iniciar();
  } catch {
    $("erro-login").textContent = t("comum.senha_incorreta");
  }
};

if (senha) iniciar();
