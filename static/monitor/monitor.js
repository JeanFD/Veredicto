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
  $("vpm-agora").textContent = `neste minuto, até agora: ${vpm.at(-1)}`;
  $("urnas").textContent = `${m.urnas.online} / ${m.urnas.ativas}`;
  $("cartao-urnas").classList.toggle("alerta", m.urnas.online < m.urnas.ativas);
  const { p50, p95 } = m.latencia_ms;
  $("latencia").textContent = p50 === null ? "—" : `${Math.round(p50)} · ${Math.round(p95)} ms`;
  $("sessao").textContent = m.sessao ? `${m.sessao.tema} · ${m.sessao.estado}` : "Nenhuma sessão ativa";
  $("total").textContent = m.sessao ? `${m.sessao.total} votos` : "—";

  const maximo = Math.max(1, ...vpm);
  $("grafico").replaceChildren(...vpm.map((n, i) => {
    const barra = document.createElement("div");
    barra.style.height = `${(n / maximo) * 100}%`;
    barra.title = `${n} votos · ${i === vpm.length - 1 ? "minuto atual" : `há ${vpm.length - 1 - i} min`}`;
    return barra;
  }));

  $("totais").replaceChildren(
    ...Object.entries(m.votos_total).map(([origem, n]) => linha(`Votos aceitos (${origem})`, n)),
    ...Object.entries(m.recusados_total).map(([motivo, n]) => linha(`Recusados (${motivo})`, n)),
  );
  if (!$("totais").children.length) $("totais").appendChild(linha("Nenhum voto ainda", ""));
  $("atualizado").textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")} · a cada 5s`;
}

async function atualizar() {
  try {
    mostrar(await buscar());
  } catch (e) {
    if (e.message === "senha") return sair();
    $("atualizado").textContent = `Sem conexão com o servidor (${new Date().toLocaleTimeString("pt-BR")})`;
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

$("entrar").onclick = async () => {
  senha = $("senha").value;
  try {
    await buscar();
    sessionStorage.setItem("senha", senha);
    iniciar();
  } catch {
    $("erro-login").textContent = "Senha incorreta";
  }
};

if (senha) iniciar();
