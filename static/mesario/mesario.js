const $ = (id) => document.getElementById(id);
let senha = sessionStorage.getItem("senha");

// ---------- API ----------
async function api(metodo, caminho, corpo) {
  const r = await fetch(caminho, {
    method: metodo,
    headers: {
      Authorization: "Basic " + btoa("mesario:" + senha),
      "Content-Type": "application/json",
    },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  const dados = await r.json().catch(() => ({}));
  if (r.status === 401 && !$("painel").hidden) sair();
  if (!r.ok) {
    const detalhe = typeof dados.detail === "string" ? dados.detail : dados.detail?.mensagem;
    const erro = new Error(detalhe ?? `Erro ${r.status}`);
    erro.status = r.status;
    erro.dados = dados;
    throw erro;
  }
  return dados;
}

function criarBotao(texto, aoClicar) {
  const b = document.createElement("button");
  b.textContent = texto;
  b.onclick = aoClicar;
  return b;
}

// ---------- Sessões ----------
const PROXIMO = {
  AGUARDANDO: "Abrir votação",
  ABERTA: "Encerrar votação",
  ENCERRADA: "Revelar resultado",
};

async function carregarSessoes() {
  const sessoes = await api("GET", "/api/admin/sessoes");
  const area = $("sessoes");
  area.innerHTML = "";
  for (const s of sessoes) {
    const linha = document.createElement("div");
    linha.className = "sessao" + (s.ativa ? " ativa" : "");
    const titulo = document.createElement("span");
    titulo.textContent = `${s.tema} · ${s.estado}`;
    linha.appendChild(titulo);
    if (!s.ativa) {
      linha.appendChild(criarBotao("Ativar", () => acao(`/api/admin/sessoes/${s.id}/ativar`)));
    } else if (PROXIMO[s.estado]) {
      linha.appendChild(criarBotao(PROXIMO[s.estado], () => avancar(s.id, s.estado)));
    }
    area.appendChild(linha);
  }
}

async function acao(caminho) {
  try {
    await api("POST", caminho);
    await carregarSessoes();
  } catch (e) {
    alert(e.message);
  }
}

async function avancar(id, estado) {
  if (!confirm(`${PROXIMO[estado]}?`)) return;
  try {
    await api("POST", `/api/admin/sessoes/${id}/avancar`);
  } catch (e) {
    const problemas = e.dados?.detail?.problemas;
    if (e.status === 409 && problemas) {
      const texto = `Há pendências:\n\n${problemas.join("\n")}\n\nRevelar mesmo assim?`;
      if (!confirm(texto)) return;
      await api("POST", `/api/admin/sessoes/${id}/avancar?forcar=true`);
    } else {
      alert(e.message);
      return;
    }
  }
  await carregarSessoes();
}

// ---------- WebSocket ----------
function conectarWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/mesario`);
  ws.onopen = () => ws.send(JSON.stringify({ senha }));
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.tipo === "snapshot" || m.tipo === "estado") {
      $("ativa").textContent = m.sessao ? `${m.sessao.tema} (${m.sessao.estado})` : "nenhuma";
      $("total").textContent = m.total;
      carregarSessoes();
    }
    if (m.tipo === "total") $("total").textContent = m.total;
    if (m.tipo === "urnas" && window.mostrarUrnas) window.mostrarUrnas(m.urnas);
  };
  ws.onclose = (e) => {
    if (e.code === 4401) return sair();
    setTimeout(conectarWs, 2000);
  };
}

// ---------- Login ----------
function sair() {
  sessionStorage.removeItem("senha");
  location.reload();
}

function iniciar() {
  $("login").hidden = true;
  $("painel").hidden = false;
  carregarSessoes();
  conectarWs();
}

$("entrar").onclick = async () => {
  senha = $("senha").value;
  try {
    await api("GET", "/api/admin/sessoes");
    sessionStorage.setItem("senha", senha);
    iniciar();
  } catch {
    $("erro-login").textContent = "Senha incorreta";
  }
};

if (senha) iniciar();


// ---------- Urnas ----------
window.mostrarUrnas = (urnas) => {
  const area = $("urnas");
  area.innerHTML = "";
  for (const u of urnas) {
    const classe = !u.ativa ? "inativa" : u.nunca_conectou ? "nunca" : u.online ? "online" : "offline";
    const situacao = !u.ativa ? "desativada"
      : u.nunca_conectou ? "nunca conectou"
      : u.online ? `${u.pendentes} pendentes`
      : `offline há ${u.segundos_sem_sinal}s`;

    const cartao = document.createElement("div");
    cartao.className = `urna ${classe}`;
    for (const texto of [`${u.id}${u.reserva ? " (reserva)" : ""}`, u.nome, `${u.votos_sessao} votos`, situacao]) {
      const linha = document.createElement("div");
      linha.textContent = texto;
      cartao.appendChild(linha);
    }
    if (u.ativa) {
      cartao.appendChild(criarBotao("Desativar", () => {
        if (confirm(`Desativar ${u.id}? Ela não poderá mais enviar votos.`)) {
          acao(`/api/admin/urnas/${u.id}/desativar`);
        }
      }));
    }
    area.appendChild(cartao);
  }
};

$("nova-urna").onsubmit = async (e) => {
  e.preventDefault();
  try {
    const { id, token } = await api("POST", "/api/admin/urnas", {
      id: $("nova-id").value,
      nome: $("nova-nome").value,
      reserva: $("nova-reserva").checked,
    });
    const link = `${location.origin}/urna/#id=${encodeURIComponent(id)}&token=${encodeURIComponent(token)}`;

    const area = $("link-urna");
    area.innerHTML = "";
    const aviso = document.createElement("p");
    aviso.textContent = `Abra na urna ${id}. Este link não será mostrado de novo.`;
    const campo = document.createElement("input");
    campo.value = link;
    campo.readOnly = true;
    campo.style.width = "100%";
    const qr = document.createElement("div");
    area.append(aviso, campo, qr);
    new QRCode(qr, { text: link, width: 220, height: 220 });

    e.target.reset();
  } catch (err) {
    alert(err.message);
  }
};