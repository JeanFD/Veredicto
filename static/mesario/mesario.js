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
    const erro = new Error(detalhe ?? t("mesario.erro", { status: r.status }));
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
  AGUARDANDO: t("mesario.abrir_votacao"),
  ABERTA: t("mesario.encerrar_votacao"),
  ENCERRADA: t("mesario.revelar_resultado"),
};
// revelar é irreversível: vai junto das ações perigosas
const PERIGOSO = new Set(["ENCERRADA"]);

function botaoAvancar(s) {
  const perigoso = PERIGOSO.has(s.estado);
  return criarBotao(PROXIMO[s.estado], () => avancar(s.id, s.estado), perigoso ? "perigo" : "principal");
}

// "Pergunta 2 de 3 · " para perguntas de questionário; vazio para sessão avulsa
const posicao = (s) => (s.total_perguntas > 1 ? t("mesario.pergunta_prefixo", { n: s.pergunta, total: s.total_perguntas }) : "");

function mostrarEstado(sessao, total) {
  $("ativa").textContent = sessao ? posicao(sessao) + sessao.tema : t("mesario.nenhuma");
  $("selo-estado").textContent = sessao ? t(`estado.${sessao.estado}`) : "—";
  $("selo-estado").className = "selo " + (sessao ? sessao.estado : "");
  $("total").textContent = total;
  $("acoes-estado").innerHTML = "";
  if (sessao && PROXIMO[sessao.estado]) $("acoes-estado").appendChild(botaoAvancar(sessao));
  // o mesário libera cada pergunta do questionário depois de revelar a anterior
  if (sessao?.estado === "REVELADA" && sessao.proxima_pergunta) {
    $("acoes-estado").appendChild(criarBotao(t("mesario.liberar_pergunta", { n: sessao.pergunta + 1 }), () => {
      if (confirm(t("mesario.confirmar_liberar", { n: sessao.pergunta + 1, total: sessao.total_perguntas }))) {
        acao(`/api/admin/sessoes/${sessao.proxima_pergunta}/ativar`);
      }
    }, "principal"));
  }
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
    titulo.textContent = `${posicao(s)}${s.tema} · ${t(`estado.${s.estado}`)}${s.arquivada ? ` · ${t("mesario.arquivada")}` : ""}`;
    linha.appendChild(titulo);

    const perigo = document.createElement("div");
    perigo.className = "acoes-perigo";
    if (s.arquivada) {
      linha.appendChild(criarBotao(t("mesario.desarquivar"), () => acao(`/api/admin/sessoes/${s.id}/desarquivar`)));
    } else if (!s.ativa && !s.liberada) {
      const aviso = document.createElement("small");
      aviso.textContent = t("mesario.aguarda_anterior");
      linha.appendChild(aviso);
    } else if (!s.ativa) {
      linha.appendChild(criarBotao(t("mesario.ativar"), () => acao(`/api/admin/sessoes/${s.id}/ativar`)));
    }
    if (!s.arquivada && !s.ativa) {
      perigo.appendChild(criarBotao(t("mesario.arquivar"), () => {
        if (confirm(t("mesario.confirmar_arquivar", { tema: s.tema }))) {
          acao(`/api/admin/sessoes/${s.id}/arquivar`);
        }
      }, "perigo"));
    } else if (s.ativa && PROXIMO[s.estado]) {
      (PERIGOSO.has(s.estado) ? perigo : linha).appendChild(botaoAvancar(s));
    }
    if (!s.arquivada && s.estado !== "REVELADA") {
      perigo.appendChild(criarBotao(t("mesario.zerar"), () => zerar(s), "perigo"));
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
    area.appendChild(criarBotao(t("mesario.criar_preset", { tema: p.tema }), () => criarSessao(p)));
  }
}

async function criarSessao(dados, caminho = "/api/admin/sessoes") {
  try {
    await api("POST", caminho, dados);
    await carregarSessoes();
    return true;
  } catch (e) {
    alert(e.message);
    return false;
  }
}

function adicionarOpcao(area, rotulo = "", cor = "#64748b") {
  const linha = document.createElement("div");
  linha.className = "opcao";
  const campo = document.createElement("input");
  campo.placeholder = t("mesario.rotulo");
  campo.required = true;
  campo.maxLength = 40;
  campo.value = rotulo;
  const seletor = document.createElement("input");
  seletor.type = "color";
  seletor.value = cor;
  linha.append(campo, seletor, criarBotao(t("mesario.remover"), () => {
    if (area.children.length > 2) linha.remove();
  }));
  area.appendChild(linha);
}

// Com mais de uma pergunta, a sessão vira um questionário: perguntas encadeadas,
// cada uma aberta, encerrada e revelada separadamente.
function adicionarPergunta() {
  const bloco = document.createElement("fieldset");
  bloco.className = "pergunta";
  const titulo = document.createElement("legend");
  const tema = document.createElement("input");
  tema.placeholder = t("mesario.tema_pergunta");
  tema.required = true;
  tema.maxLength = 200;
  const opcoes = document.createElement("div");
  const remover = criarBotao(t("mesario.remover_pergunta"), () => { bloco.remove(); numerarPerguntas(); });
  remover.className = "remover-pergunta";
  bloco.append(titulo, tema, opcoes, criarBotao(t("mesario.mais_opcao"), () => adicionarOpcao(opcoes)), remover);
  adicionarOpcao(opcoes, t("mesario.opcao_padrao_1"), "#dc2626");
  adicionarOpcao(opcoes, t("mesario.opcao_padrao_2"), "#2563eb");
  $("perguntas").appendChild(bloco);
  numerarPerguntas();
}

function numerarPerguntas() {
  const blocos = [...$("perguntas").children];
  blocos.forEach((b, i) => {
    b.querySelector("legend").textContent = blocos.length > 1 ? t("mesario.legenda_pergunta", { n: i + 1 }) : "";
    b.querySelector(".remover-pergunta").hidden = blocos.length === 1;
  });
}

function reiniciarFormularioSessao() {
  $("perguntas").innerHTML = "";
  adicionarPergunta();
}

$("mais-pergunta").onclick = adicionarPergunta;

$("nova-sessao").onsubmit = async (e) => {
  e.preventDefault();
  const perguntas = [];
  for (const bloco of $("perguntas").children) {
    const opcoes = [...bloco.querySelectorAll(".opcao")].map((linha) => {
      const [rotulo, cor] = linha.querySelectorAll("input");
      return { rotulo: rotulo.value.trim(), cor: cor.value };
    });
    const tema = bloco.querySelector("input").value.trim();
    if (opcoes.some((o) => !o.rotulo)) return alert(t("mesario.preencha_opcoes", { tema }));
    if (new Set(opcoes.map((o) => o.rotulo.toLowerCase())).size !== opcoes.length) {
      return alert(t("mesario.opcoes_repetidas", { tema }));
    }
    perguntas.push({ tema, opcoes });
  }
  const criada = perguntas.length === 1
    ? await criarSessao(perguntas[0])
    : await criarSessao({ perguntas }, "/api/admin/questionarios");
  if (criada) reiniciarFormularioSessao();
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
  const confirmacao = prompt(t("mesario.confirmar_zerar", { tema: s.tema }));
  if (confirmacao === null) return;
  try {
    const { apagados } = await api("POST", `/api/admin/sessoes/${s.id}/zerar`, { confirmacao });
    alert(t("mesario.votos_apagados", { n: apagados }));
    await carregarSessoes();
  } catch (e) {
    alert(e.message);
  }
}

async function avancar(id, estado) {
  if (!confirm(t("mesario.confirmar_acao", { acao: PROXIMO[estado] }))) return;
  try {
    await api("POST", `/api/admin/sessoes/${id}/avancar`);
  } catch (e) {
    const problemas = e.dados?.detail?.problemas;
    if (e.status === 409 && problemas) {
      const texto = t("mesario.pendencias", { problemas: problemas.join("\n") });
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
    $("erro-login").textContent = t("comum.senha_incorreta");
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
    const situacao = !u.ativa ? t("mesario.desativada")
      : u.nunca_conectou ? t("mesario.nunca_conectou")
      : u.online ? t("mesario.n_pendentes", { n: u.pendentes })
      : t("mesario.offline_ha", { s: u.segundos_sem_sinal });

    const cartao = document.createElement("div");
    cartao.className = `urna ${classe}`;
    for (const texto of [`${u.id}${u.reserva ? t("mesario.reserva_marca") : ""}`, u.nome, t("mesario.n_votos", { n: u.votos_sessao }), situacao]) {
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
    if (u.ativa) {
      // ações raras e perigosas recolhidas, para não competir com o status
      const acoes = document.createElement("details");
      const titulo = document.createElement("summary");
      titulo.textContent = t("mesario.acoes");
      acoes.appendChild(titulo);
      acoes.open = urnasComAcoesAbertas.has(u.id);
      acoes.ontoggle = () => {
        if (acoes.open) urnasComAcoesAbertas.add(u.id);
        else urnasComAcoesAbertas.delete(u.id);
      };
      cartao.appendChild(acoes);
      acoes.appendChild(criarBotao(t("mesario.gerar_link"), async () => {
        if (!confirm(t("mesario.confirmar_link", { id: u.id }))) return;
        try {
          const { id, token } = await api("POST", `/api/admin/urnas/${u.id}/novo-token`);
          prepararLink(id, token);
        } catch (e) {
          alert(e.message);
        }
      }, "perigo"));
      acoes.appendChild(criarBotao(t("mesario.desativar"), () => {
        if (confirm(t("mesario.confirmar_desativar", { id: u.id }))) {
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

// ---------- Telão ----------
$("abrir-telao").onclick = async () => {
  // abre a aba antes do await para o navegador não bloquear o pop-up
  const aba = window.open("about:blank", "_blank");
  try {
    const { chave } = await api("GET", "/api/admin/telao");
    aba.location = `/telao/#chave=${encodeURIComponent(chave)}`;
  } catch (e) {
    aba.close();
    alert(e.message);
  }
};

// ---------- Importar fila ----------
const MOTIVOS = ["sessao_encerrada", "sessao_nao_aberta", "sessao_inexistente", "opcao_invalida"];

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
    return resumirImportacao([t("mesario.arquivo_invalido", { arquivo: arquivo.name })], true);
  }
  if (dados?.formato !== "veredicto-fila" || !Array.isArray(dados.votos) || !dados.urna_id) {
    return resumirImportacao([t("mesario.nao_e_fila", { arquivo: arquivo.name })], true);
  }
  if (!confirm(t("mesario.confirmar_importar", { n: dados.votos.length, urna: dados.urna_id }))) return;

  try {
    const r = await api("POST", "/api/admin/importar", { urna_id: dados.urna_id, votos: dados.votos });
    const porMotivo = {};
    for (const v of r.recusados) porMotivo[v.motivo] = (porMotivo[v.motivo] ?? 0) + 1;
    resumirImportacao([
      t("mesario.importacao_origem", { urna: dados.urna_id, quando: new Date(dados.exportado_em).toLocaleString(document.documentElement.lang) }),
      t("mesario.importacao_aceitos", { n: r.aceitos }),
      t("mesario.importacao_existentes", { n: r.existentes }),
      t("mesario.importacao_recusados", { n: r.recusados.length }),
      ...Object.entries(porMotivo).map(([m, n]) => t("mesario.importacao_motivo", {
        n, motivo: MOTIVOS.includes(m) ? t(`mesario.motivo.${m}`) : m,
      })),
    ]);
  } catch (err) {
    const msg = err.status === 422 ? t("mesario.formato_invalido") : err.message;
    resumirImportacao([t("mesario.falha_importar", { erro: msg })], true);
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
    aviso.textContent = t("mesario.link_pronto", { id });
    area.append(aviso, criarBotao(t("mesario.mostrar_link"), mostrar), criarBotao(t("mesario.descartar"), descartar));
  };

  const mostrar = () => {
    area.innerHTML = "";
    const aviso = document.createElement("p");
    aviso.textContent = t("mesario.abra_na_urna", { id, s: SEGUNDOS_VISIVEL });
    const campo = document.createElement("input");
    campo.value = link;
    campo.readOnly = true;
    campo.style.width = "100%";
    const qr = document.createElement("div");
    area.append(aviso, campo, qr, criarBotao(t("mesario.ocultar"), ocultar));
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