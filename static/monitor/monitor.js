const $ = (id) => document.getElementById(id);

async function buscar(caminho) {
  const r = await fetch(caminho, { headers: autorizacao() });
  if (r.status === 401) throw new Error("senha");
  return r.json();
}

function mostrarUrnas(urnas) {
  $("grade-urnas").replaceChildren(...urnas.filter((u) => u.ativa).map((u) => {
    const cartao = document.createElement("div");
    cartao.className = `urna ${u.nunca_conectou ? "nunca" : u.online ? "online" : "offline"}`;
    const situacao = u.nunca_conectou ? t("mesario.nunca_conectou")
      : u.online ? t("mesario.n_pendentes", { n: u.pendentes })
      : t("mesario.offline_ha", { s: u.segundos_sem_sinal });
    for (const texto of [u.id, u.nome, t("mesario.n_votos", { n: u.votos_sessao }), situacao]) {
      const linha = document.createElement("div");
      linha.textContent = texto;
      cartao.appendChild(linha);
    }
    if (u.recusados) {
      const alerta = document.createElement("div");
      alerta.className = "recusados";
      alerta.textContent = t("mesario.n_recusados", { n: u.recusados });
      cartao.appendChild(alerta);
    }
    return cartao;
  }));
  if (!$("grade-urnas").children.length) {
    const aviso = document.createElement("p");
    aviso.className = "vazio";
    aviso.textContent = t("mesario.sem_urnas");
    $("grade-urnas").appendChild(aviso);
  }
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
    const [metricas, urnas] = await Promise.all([buscar("/api/admin/metricas"), buscar("/api/admin/urnas")]);
    mostrar(metricas);
    mostrarUrnas(urnas);
  } catch (e) {
    if (e.message === "senha") return sair();
    $("atualizado").textContent = t("monitor.sem_conexao", { hora: new Date().toLocaleTimeString(document.documentElement.lang) });
  }
}

function sair() {
  sessionStorage.removeItem("login");
  location.reload();
}

function iniciar() {
  $("login").hidden = true;
  $("painel").hidden = false;
  mostrarSair(sair);
  atualizar();
  setInterval(atualizar, 5000);
}

prepararLogin(iniciar);

if (lerLogin()) iniciar();
