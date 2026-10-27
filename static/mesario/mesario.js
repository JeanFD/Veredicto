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

function criarBotao(texto, aoClicar, classe) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = texto;
  b.onclick = aoClicar;
  if (classe) b.className = classe;
  return b;
}

// ---------- Sessões ----------
const PROXIMO = {
  AGUARDANDO: "Abrir votação",
  ABERTA: "Encerrar votação",
  ENCERRADA: "Revelar resultado",
};
// revelar é irreversível: vai junto das ações perigosas
const PERIGOSO = new Set(["ENCERRADA"]);

function botaoAvancar(s) {
  const perigoso = PERIGOSO.has(s.estado);
  return criarBotao(PROXIMO[s.estado], () => avancar(s.id, s.estado), perigoso ? "perigo" : "principal");
}

function mostrarEstado(sessao, total) {
  $("ativa").textContent = sessao ? sessao.tema : "nenhuma";
  $("selo-estado").textContent = sessao ? sessao.estado : "—";
  $("selo-estado").className = "selo " + (sessao ? sessao.estado : "");
  $("total").textContent = total;
  $("acoes-estado").innerHTML = "";
  if (sessao && PROXIMO[sessao.estado]) $("acoes-estado").appendChild(botaoAvancar(sessao));
}

async function carregarSessoes() {
  // lista completa: os presets precisam conhecer também os temas arquivados
  const sessoes = await api("GET", "/api/admin/sessoes?arquivadas=true");
  const mostrarArquivadas = $("mostrar-arquivadas").checked;
  const area = $("sessoes");
  area.innerHTML = "";
  for (const s of sessoes.filter((s) => mostrarArquivadas || !s.arquivada)) {
    const linha = document.createElement("div");
    linha.className = "sessao" + (s.ativa ? " ativa" : "") + (s.arquivada ? " arquivada" : "");
    const titulo = document.createElement("span");
    titulo.textContent = `${s.tema} · ${s.estado}${s.arquivada ? " · arquivada" : ""}`;
    linha.appendChild(titulo);

    const perigo = document.createElement("div");
    perigo.className = "acoes-perigo";
    if (s.arquivada) {
      linha.appendChild(criarBotao("Desarquivar", () => acao(`/api/admin/sessoes/${s.id}/desarquivar`)));
    } else if (!s.ativa) {
      linha.appendChild(criarBotao("Ativar", () => acao(`/api/admin/sessoes/${s.id}/ativar`)));
      perigo.appendChild(criarBotao("Arquivar", () => {
        if (confirm(`Arquivar "${s.tema}"? Ela some da lista, mas pode ser desarquivada.`)) {
          acao(`/api/admin/sessoes/${s.id}/arquivar`);
        }
      }, "perigo"));
    } else if (PROXIMO[s.estado]) {
      (PERIGOSO.has(s.estado) ? perigo : linha).appendChild(botaoAvancar(s));
    }
    if (!s.arquivada && s.estado !== "REVELADA") {
      perigo.appendChild(criarBotao("Zerar", () => zerar(s), "perigo"));
    }
    if (perigo.children.length) linha.appendChild(perigo);
    area.appendChild(linha);
  }
  const arquivadas = sessoes.filter((s) => s.arquivada).length;
  $("total-arquivadas").textContent = arquivadas ? `(${arquivadas})` : "";
  mostrarPresets(sessoes);
}

$("mostrar-arquivadas").onchange = carregarSessoes;

// ---------- Criar sessão ----------
let presets = [];

function mostrarPresets(sessoes) {
  const existentes = new Set(sessoes.map((s) => s.tema.toLowerCase()));
  const area = $("presets");
  area.innerHTML = "";
  for (const p of presets.filter((p) => !existentes.has(p.tema.toLowerCase()))) {
    area.appendChild(criarBotao(`Criar: ${p.tema}`, () => criarSessao(p)));
  }
}

async function criarSessao(dados) {
  try {
    await api("POST", "/api/admin/sessoes", dados);
    await carregarSessoes();
    return true;
  } catch (e) {
    alert(e.message);
    return false;
  }
}

function adicionarOpcao(rotulo = "", cor = "#64748b") {
  const linha = document.createElement("div");
  linha.className = "opcao";
  const campo = document.createElement("input");
  campo.placeholder = "rótulo";
  campo.required = true;
  campo.maxLength = 40;
  campo.value = rotulo;
  const seletor = document.createElement("input");
  seletor.type = "color";
  seletor.value = cor;
  linha.append(campo, seletor, criarBotao("remover", () => {
    if ($("sessao-opcoes").children.length > 2) linha.remove();
  }));
  $("sessao-opcoes").appendChild(linha);
}

function reiniciarFormularioSessao() {
  $("nova-sessao").reset();
  $("sessao-opcoes").innerHTML = "";
  adicionarOpcao("Acusação", "#dc2626");
  adicionarOpcao("Defesa", "#2563eb");
}

$("mais-opcao").onclick = () => adicionarOpcao();

$("nova-sessao").onsubmit = async (e) => {
  e.preventDefault();
  const opcoes = [...$("sessao-opcoes").children].map((linha) => {
    const [rotulo, cor] = linha.querySelectorAll("input");
    return { rotulo: rotulo.value.trim(), cor: cor.value };
  });
  if (opcoes.some((o) => !o.rotulo)) return alert("Preencha todas as opções");
  if (new Set(opcoes.map((o) => o.rotulo.toLowerCase())).size !== opcoes.length) {
    return alert("Há opções repetidas");
  }
  if (await criarSessao({ tema: $("sessao-tema").value.trim(), opcoes })) reiniciarFormularioSessao();
};

reiniciarFormularioSessao();

async function acao(caminho) {
  try {
    await api("POST", caminho);
    await carregarSessoes();
  } catch (e) {
    alert(e.message);
  }
}

async function zerar(s) {
  const confirmacao = prompt(
    `Zerar apaga TODOS os votos de "${s.tema}" e volta a sessão para AGUARDANDO.\n\n` +
    "Para confirmar, digite o tema da sessão:"
  );
  if (confirmacao === null) return;
  try {
    const { apagados } = await api("POST", `/api/admin/sessoes/${s.id}/zerar`, { confirmacao });
    alert(`${apagados} votos apagados.`);
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
      mostrarEstado(m.sessao, m.total);
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
  api("GET", "/api/admin/presets")
    .then((p) => { presets = p; }, () => {})
    .finally(carregarSessoes);
  // a grade chega pelo WebSocket a cada 5s; busca já para não abrir vazia
  api("GET", "/api/admin/urnas").then((u) => window.mostrarUrnas(u), () => {});
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
// a grade é redesenhada a cada 5s: lembra quais menus de ações estavam abertos
const urnasComAcoesAbertas = new Set();

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
    if (u.recusados) {
      const alerta = document.createElement("div");
      alerta.className = "recusados";
      alerta.textContent = `${u.recusados} votos recusados`;
      cartao.appendChild(alerta);
    }
    if (u.ativa) {
      // ações raras e perigosas recolhidas, para não competir com o status
      const acoes = document.createElement("details");
      const titulo = document.createElement("summary");
      titulo.textContent = "Ações";
      acoes.appendChild(titulo);
      acoes.open = urnasComAcoesAbertas.has(u.id);
      acoes.ontoggle = () => {
        if (acoes.open) urnasComAcoesAbertas.add(u.id);
        else urnasComAcoesAbertas.delete(u.id);
      };
      cartao.appendChild(acoes);
      acoes.appendChild(criarBotao("Gerar novo link", async () => {
        if (!confirm(`Gerar novo link para ${u.id}? O link atual deixa de funcionar e a urna precisa ser reconfigurada.`)) return;
        try {
          const { id, token } = await api("POST", `/api/admin/urnas/${u.id}/novo-token`);
          prepararLink(id, token);
        } catch (e) {
          alert(e.message);
        }
      }, "perigo"));
      acoes.appendChild(criarBotao("Desativar", () => {
        if (confirm(`Desativar ${u.id}? Ela não poderá mais enviar votos.`)) {
          acao(`/api/admin/urnas/${u.id}/desativar`);
        }
      }, "perigo"));
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
    prepararLink(id, token);
    e.target.reset();
  } catch (err) {
    alert(err.message);
  }
};

// ---------- Importar fila ----------
const MOTIVOS = {
  sessao_encerrada: "feitos depois do encerramento ou com a sessão já revelada",
  sessao_nao_aberta: "sessão ainda não aberta",
  sessao_inexistente: "sessão inexistente",
  opcao_invalida: "opção inválida",
};

function resumirImportacao(linhas, erro = false) {
  const area = $("resumo-importacao");
  area.innerHTML = "";
  for (const texto of linhas) {
    const p = document.createElement("div");
    p.textContent = texto;
    if (erro) p.className = "erro";
    area.appendChild(p);
  }
}

$("arquivo-fila").onchange = async (e) => {
  const arquivo = e.target.files[0];
  e.target.value = "";
  if (!arquivo) return;

  let dados;
  try {
    dados = JSON.parse(await arquivo.text());
  } catch {
    return resumirImportacao([`${arquivo.name}: não é um arquivo JSON válido.`], true);
  }
  if (dados?.formato !== "veredicto-fila" || !Array.isArray(dados.votos) || !dados.urna_id) {
    return resumirImportacao([`${arquivo.name}: não é uma fila exportada pela urna.`], true);
  }
  if (!confirm(`Importar ${dados.votos.length} votos da urna ${dados.urna_id}?`)) return;

  try {
    const r = await api("POST", "/api/admin/importar", { urna_id: dados.urna_id, votos: dados.votos });
    const porMotivo = {};
    for (const v of r.recusados) porMotivo[v.motivo] = (porMotivo[v.motivo] ?? 0) + 1;
    resumirImportacao([
      `Urna ${dados.urna_id} · arquivo de ${new Date(dados.exportado_em).toLocaleString("pt-BR")}`,
      `${r.aceitos} votos aceitos`,
      `${r.existentes} já estavam no servidor (não duplicados)`,
      `${r.recusados.length} recusados`,
      ...Object.entries(porMotivo).map(([m, n]) => `  · ${n} ${MOTIVOS[m] ?? m}`),
    ]);
  } catch (err) {
    const msg = err.status === 422 ? "o arquivo tem votos em formato inválido" : err.message;
    resumirImportacao([`Falha ao importar: ${msg}.`], true);
  }
};

// O link carrega o token da urna: fica oculto até o mesário pedir,
// some sozinho após um minuto à mostra e é descartado de vez em 10 minutos.
const SEGUNDOS_VISIVEL = 60;
const MINUTOS_DISPONIVEL = 10;
let temporizadores = [];

function prepararLink(id, token) {
  temporizadores.forEach(clearTimeout);
  const link = `${location.origin}/urna/#id=${encodeURIComponent(id)}&token=${encodeURIComponent(token)}`;
  const area = $("link-urna");

  const ocultar = () => {
    area.innerHTML = "";
    const aviso = document.createElement("p");
    aviso.textContent = `Link da urna ${id} pronto. Mostre só na hora de configurar a urna.`;
    area.append(aviso, criarBotao("Mostrar link e QR code", mostrar), criarBotao("Descartar", descartar));
  };

  const mostrar = () => {
    area.innerHTML = "";
    const aviso = document.createElement("p");
    aviso.textContent = `Abra na urna ${id}. Oculta sozinho em ${SEGUNDOS_VISIVEL}s.`;
    const campo = document.createElement("input");
    campo.value = link;
    campo.readOnly = true;
    campo.style.width = "100%";
    const qr = document.createElement("div");
    area.append(aviso, campo, qr, criarBotao("Ocultar", ocultar));
    new QRCode(qr, { text: link, width: 220, height: 220 });
    temporizadores.push(setTimeout(() => { if (area.contains(campo)) ocultar(); }, SEGUNDOS_VISIVEL * 1000));
  };

  const descartar = () => {
    temporizadores.forEach(clearTimeout);
    area.innerHTML = "";
  };

  ocultar();
  temporizadores = [setTimeout(descartar, MINUTOS_DISPONIVEL * 60 * 1000)];
}