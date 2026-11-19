const $ = (id) => document.getElementById(id);

// ---------- API ----------
async function api(metodo, caminho, corpo) {
  let r;
  try {
    r = await fetch(caminho, {
      method: metodo,
      headers: { ...autorizacao(), "Content-Type": "application/json" },
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
  } catch {
    // sem isso a falha de rede chega à tela como "Failed to fetch", em inglês
    throw new Error(t("login.sem_conexao"));
  }
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

function vazio(texto) {
  const aviso = document.createElement("p");
  aviso.className = "vazio";
  aviso.textContent = texto;
  return aviso;
}

// ---------- Abas ----------
// a aba aberta fica no endereço (#urnas): recarregar ou voltar mantém o lugar
const ABAS = ["sessoes", "nova", "urnas", "cartoes", "telao", "contas", "registro"];

// clicar numa aba empilha o endereço, então o voltar do navegador desfaz a troca;
// a volta chega aqui pelo hashchange
function mostrarAba(nome, empilhar = false) {
  if (!ABAS.includes(nome)) nome = ABAS[0];
  for (const b of document.querySelectorAll("[data-aba]")) b.setAttribute("aria-selected", b.dataset.aba === nome);
  for (const p of document.querySelectorAll("[data-painel]")) p.hidden = p.dataset.painel !== nome;
  const endereco = nome === ABAS[0] ? location.pathname : `#${nome}`;
  const mudou = endereco !== (location.hash || location.pathname);
  history[empilhar && mudou ? "pushState" : "replaceState"](null, "", endereco);
  // o Registro busca os eventos toda vez que a aba abre — por clique, pelo endereço
  // ou pelo voltar do navegador. Antes só o clique carregava, então recarregar a
  // página em #registro mostrava a tabela vazia.
  if (nome === "registro" && lerLogin()) carregarRegistro();
}

for (const b of document.querySelectorAll("[data-aba]")) b.onclick = () => mostrarAba(b.dataset.aba, true);
mostrarAba(location.hash.slice(1));
addEventListener("hashchange", () => mostrarAba(location.hash.slice(1)));

function criarBotao(texto, aoClicar, classe) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = texto;
  b.onclick = aoClicar;
  if (classe) b.className = classe;
  return b;
}

// ---------- Sessões ----------
// A barra de cima é o palco: a sessão em cena, a trilha dos quatro estados e um
// único botão, o próximo passo. A lista abaixo serve para escolher quem entra em
// cena; arquivar, zerar e mover de caso ficam guardados em "Ações".
const ESTADOS = ["AGUARDANDO", "ABERTA", "ENCERRADA", "REVELADA"];
// cada passo leva o aviso do que ele faz: antes a confirmação era só "Revelar
// resultado?", a mesma pergunta seca para abrir a votação e para revelá-la
const PROXIMO = {
  AGUARDANDO: { rotulo: t("mesario.abrir_votacao"), aviso: t("mesario.aviso_abrir") },
  ABERTA: { rotulo: t("mesario.encerrar_votacao"), aviso: t("mesario.aviso_encerrar") },
  ENCERRADA: { rotulo: t("mesario.revelar_resultado"), aviso: t("mesario.aviso_revelar") },
};
// revelar é irreversível: sai em vermelho
const PERIGOSO = new Set(["ENCERRADA"]);

let casoFiltro = "";
let casosConhecidos = [];
let sessoesCarregadas = [];
const sessoesComAcoesAbertas = new Set();

// "Pergunta 2 de 3 · " para perguntas de questionário; vazio para sessão avulsa
const posicao = (s) => (s.total_perguntas > 1 ? t("mesario.pergunta_prefixo", { n: s.pergunta, total: s.total_perguntas }) : "");

function selo(classe, texto) {
  const marca = document.createElement("span");
  marca.className = `selo ${classe}`;
  marca.textContent = texto;
  return marca;
}

// ---------- Barra: o que está em cena ----------
function botaoProximoPasso(s) {
  if (PROXIMO[s.estado]) {
    return criarBotao(PROXIMO[s.estado].rotulo, () => avancar(s), PERIGOSO.has(s.estado) ? "perigo" : "principal");
  }
  // revelada a pergunta, o próximo passo é a seguinte do mesmo questionário
  if (s.estado === "REVELADA" && s.proxima_pergunta) {
    const liberar = t("mesario.ativar_pergunta", { n: s.pergunta + 1 });
    return criarBotao(liberar, async () => {
      const sim = await confirmar({
        titulo: liberar, acao: liberar,
        texto: t("mesario.confirmar_liberar", { n: s.pergunta + 1, total: s.total_perguntas }),
      });
      if (sim !== null) acao(`/api/admin/sessoes/${s.proxima_pergunta}/ativar`);
    }, "principal");
  }
  return null;
}

function mostrarTrilha(sessao) {
  $("trilha").hidden = !sessao;
  if (!sessao) return;
  const atual = ESTADOS.indexOf(sessao.estado);
  $("trilha").replaceChildren(...ESTADOS.map((estado, i) => {
    const passo = document.createElement("li");
    passo.className = i < atual ? "feito" : i === atual ? "agora" : "";
    passo.textContent = t(`estado.${estado}`);
    if (i === atual) passo.setAttribute("aria-current", "step");
    return passo;
  }));
}

function mostrarEstado(sessao, total) {
  // o caso fica na linha de cima, com o rótulo; o tema embaixo, inteiro
  $("caso-ativo").textContent = sessao?.caso ?? "";
  $("ativa").textContent = sessao ? posicao(sessao) + sessao.tema : t("mesario.nenhuma");
  $("selo-estado").textContent = sessao ? t(`estado.${sessao.estado}`) : "—";
  $("selo-estado").className = "selo " + (sessao ? sessao.estado : "");
  $("selo-teste").hidden = !sessao?.teste;
  mostrarTrilha(sessao);
  $("chave-celular").hidden = !sessao;
  $("campo-peso-celular").hidden = !sessao?.celular;
  $("peso-celular").value = sessao?.peso_celular ?? 1;
  $("peso-celular").onchange = async (e) => {
    try {
      await api("POST", `/api/admin/sessoes/${sessao.id}/peso-celular`, { peso: Number(e.target.value) });
      await carregarSessoes();
    } catch (erro) {
      e.target.value = sessao.peso_celular;
      avisarErro(erro.status === 422 ? t("mesario.peso_invalido") : erro.message);
    }
  };
  $("alternar-celular").checked = !!sessao?.celular;
  $("alternar-celular").onchange = async (e) => {
    try {
      await api("POST", `/api/admin/sessoes/${sessao.id}/celular`, { ativo: e.target.checked });
      await carregarSessoes();
    } catch (erro) {
      e.target.checked = !e.target.checked;
      avisarErro(erro.message);
    }
  };
  $("total").textContent = total;
  const proximo = sessao && botaoProximoPasso(sessao);
  $("acoes-estado").replaceChildren(...(proximo ? [proximo] : []));
}

// ---------- Lista: quem entra em cena ----------
async function carregarSessoes() {
  mostrarSessoes(await api("GET", "/api/admin/sessoes?arquivadas=true"));
}

function mostrarSessoes(sessoes) {
  sessoesCarregadas = sessoes;
  atualizarCasos();
  // a barra sai da mesma lista: as duas nunca mostram estados diferentes
  const emCena = sessoes.find((s) => s.ativa);
  mostrarEstado(emCena ?? null, emCena ? emCena.votos : 0);

  const visiveis = sessoes.filter((s) => ($("mostrar-arquivadas").checked || !s.arquivada)
    && (!casoFiltro || (s.caso || "") === casoFiltro));
  const area = $("sessoes");
  area.replaceChildren(...porCaso(visiveis).map(blocoDoCaso));
  if (!area.children.length) area.appendChild(vazio(t(casoFiltro ? "mesario.sem_sessoes_no_caso" : "mesario.sem_sessoes")));

  testes.sessoes = sessoes.filter((s) => s.teste).length;
  mostrarLimparTestes();
  const arquivadas = sessoes.filter((s) => s.arquivada).length;
  $("total-arquivadas").textContent = arquivadas ? `(${arquivadas})` : "";
  mostrarPresets(sessoes);
}

// um bloco por caso, e dentro dele as perguntas de cada questionário juntas, na ordem
function porCaso(sessoes) {
  const casos = new Map();
  for (const s of sessoes) {
    const caso = s.caso || "";
    if (!casos.has(caso)) casos.set(caso, new Map());
    const grupos = casos.get(caso);
    const chave = s.grupo_id ?? `avulsa-${s.id}`;
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(s);
  }
  return [...casos].map(([caso, grupos]) => ({ caso, grupos: [...grupos.values()] }));
}

function blocoDoCaso({ caso, grupos }) {
  const bloco = document.createElement("section");
  bloco.className = "cartao caso";
  const nome = document.createElement("h2");
  nome.textContent = caso || t("mesario.sem_caso");
  bloco.appendChild(nome);
  for (const grupo of grupos) {
    if (grupo[0].total_perguntas > 1) {
      const aviso = document.createElement("p");
      aviso.className = "suave questionario";
      aviso.textContent = t("mesario.questionario_de", { n: grupo[0].total_perguntas });
      bloco.appendChild(aviso);
    }
    for (const s of grupo) bloco.appendChild(linhaSessao(s));
  }
  return bloco;
}

function linhaSessao(s) {
  const linha = document.createElement("div");
  linha.className = "sessao" + (s.ativa ? " ativa" : "") + (s.arquivada ? " arquivada" : "");
  const titulo = document.createElement("div");
  titulo.className = "titulo";
  if (s.total_perguntas > 1) {
    const passo = document.createElement("span");
    passo.className = "passo";
    passo.textContent = s.pergunta;
    titulo.appendChild(passo);
  }
  const nome = document.createElement("span");
  nome.textContent = s.tema + (s.arquivada ? ` · ${t("mesario.arquivada")}` : "");
  titulo.append(nome, selo(s.estado, t(`estado.${s.estado}`)));
  if (s.teste) titulo.appendChild(selo("teste", t("mesario.selo_teste")));
  if (s.celular) titulo.appendChild(selo("celular", t("mesario.selo_celular")));
  linha.appendChild(titulo);

  if (s.ativa) {
    const aviso = document.createElement("strong");
    aviso.className = "em-cena";
    aviso.textContent = t("mesario.em_cena");
    linha.appendChild(aviso);
  } else if (s.arquivada) {
    linha.appendChild(criarBotao(t("mesario.desarquivar"), () => acao(`/api/admin/sessoes/${s.id}/desarquivar`)));
  } else if (!s.liberada) {
    const aviso = document.createElement("small");
    aviso.className = "suave";
    aviso.textContent = t("mesario.aguarda_anterior");
    linha.appendChild(aviso);
  } else {
    linha.appendChild(criarBotao(t("mesario.ativar"), () => acao(`/api/admin/sessoes/${s.id}/ativar`)));
  }
  linha.appendChild(acoesDaSessao(s));
  return linha;
}

function acoesDaSessao(s) {
  const acoes = document.createElement("details");
  acoes.className = "acoes";
  const titulo = document.createElement("summary");
  titulo.textContent = t("mesario.acoes");
  acoes.appendChild(titulo);
  acoes.open = sessoesComAcoesAbertas.has(s.id);
  acoes.ontoggle = () => (acoes.open ? sessoesComAcoesAbertas.add(s.id) : sessoesComAcoesAbertas.delete(s.id));
  acoes.appendChild(criarBotao(t("mesario.clonar"), () => clonarSessao(s)));
  if (s.estado === "REVELADA") acoes.appendChild(criarBotao(t("mesario.baixar_votos"), () => baixarVotos(s)));
  acoes.appendChild(apagarSessao(s));
  if (s.arquivada) return acoes;
  // revelada, a sessão em cena já pode ser guardada sem precisar ativar outra
  if (!s.ativa || s.estado === "REVELADA") {
    acoes.appendChild(criarBotao(t("mesario.arquivar"), async () => {
      const sim = await confirmar({
        titulo: t("mesario.arquivar"), acao: t("mesario.arquivar"),
        texto: t("mesario.confirmar_arquivar", { tema: s.tema }),
      });
      if (sim !== null) acao(`/api/admin/sessoes/${s.id}/arquivar`);
    }, "perigo"));
  }
  // zerar só faz sentido com votos para apagar
  if (s.votos && s.estado !== "REVELADA") {
    acoes.appendChild(criarBotao(t("mesario.zerar"), () => zerar(s), "perigo so-admin"));
  }
  acoes.appendChild(seletorDeCaso(s));
  return acoes;
}

// O CSV existe no servidor desde sempre e não tinha botão nenhum. Pela barra de
// endereços também não dava: o download precisa do cabeçalho de autorização. O
// servidor só o entrega depois da revelação, então o botão só aparece aí.
async function baixarVotos(s) {
  let r;
  try {
    r = await fetch(`/api/admin/sessoes/${s.id}/votos.csv`, { headers: autorizacao() });
  } catch {
    return avisarErro(t("login.sem_conexao"));
  }
  if (!r.ok) {
    const dados = await r.json().catch(() => ({}));
    const detalhe = typeof dados.detail === "string" ? dados.detail : dados.detail?.mensagem;
    return avisarErro(detalhe ?? t("mesario.erro", { status: r.status }));
  }
  const endereco = URL.createObjectURL(await r.blob());
  const link = document.createElement("a");
  link.href = endereco;
  link.download = `sessao-${s.id}-votos.csv`;
  link.click();
  URL.revokeObjectURL(endereco);
  avisarFeito(t("mesario.votos_baixados", { arquivo: link.download }));
}

function seletorDeCaso(s) {
  const rotulo = document.createElement("label");
  rotulo.className = "mover";
  const escolha = document.createElement("select");
  escolha.setAttribute("aria-label", t("mesario.mover_caso"));
  escolha.replaceChildren(new Option(t("mesario.sem_caso"), ""), ...casosConhecidos.map((c) => new Option(c)));
  escolha.value = s.caso || "";
  escolha.onchange = () => acao(`/api/admin/sessoes/${s.id}`, "PATCH", { caso: escolha.value });
  rotulo.append(t("mesario.mover_caso"), escolha);
  return rotulo;
}

// ---------- Caso: o mesmo recorte vale para sessões e cartões ----------
function atualizarCasos() {
  const dosCartoes = cartoesCarregados.map((c) => c.pasta);
  casosConhecidos = [...new Set([...sessoesCarregadas.map((s) => s.caso), ...dosCartoes].filter(Boolean))].sort();
  for (const filtro of [$("filtro-caso"), $("filtro-caso-cartoes")]) {
    filtro.replaceChildren(new Option(t("mesario.todos_casos"), ""), ...casosConhecidos.map((c) => new Option(c)));
    filtro.value = casoFiltro;
  }
  $("casos").replaceChildren(...casosConhecidos.map((c) => new Option(c)));
}

function escolherCaso(valor) {
  casoFiltro = valor;
  mostrarSessoes(sessoesCarregadas);
  mostrarCartoes(cartoesCarregados);
}

$("filtro-caso").onchange = (e) => escolherCaso(e.target.value);
$("filtro-caso-cartoes").onchange = (e) => escolherCaso(e.target.value);
$("atalho-nova").onclick = () => {
  mostrarAba("nova");
  $("nova-caso").value = casoFiltro;
};

$("mostrar-arquivadas").onchange = carregarSessoes;

// ---------- Modo teste ----------
const testes = { sessoes: 0, urnas: 0 };

function mostrarLimparTestes() {
  const n = testes.sessoes + testes.urnas;
  $("limpar-testes").hidden = !n;
  $("limpar-testes").textContent = t("mesario.limpar_testes", { n });
}

$("limpar-testes").onclick = async () => {
  const rotulo = t("mesario.limpar_testes", { n: testes.sessoes + testes.urnas });
  const sim = await confirmar({
    titulo: rotulo, acao: rotulo, perigo: true,
    texto: t("mesario.confirmar_limpar", testes),
  });
  if (sim === null) return;
  try {
    const r = await api("POST", "/api/admin/testes/limpar");
    avisarFeito(t("mesario.testes_limpos", r));
    await carregarSessoes();
    window.mostrarUrnas(await api("GET", "/api/admin/urnas"));
  } catch (e) {
    avisarErro(e.message);
  }
};

// ---------- Criar sessão ----------
let presets = [];

function mostrarPresets(sessoes) {
  const existentes = new Set(sessoes.map((s) => s.tema.toLowerCase()));
  const area = $("presets");
  area.innerHTML = "";
  for (const p of presets.filter((p) => !existentes.has(p.tema.toLowerCase()))) {
    area.appendChild(criarBotao(t("mesario.criar_preset", { tema: p.tema }), async () => {
      if (await criarSessao(p)) mostrarAba("sessoes");
    }));
  }
}

async function criarSessao(dados, caminho = "/api/admin/sessoes") {
  try {
    await api("POST", caminho, dados);
    await carregarSessoes();
    return true;
  } catch (e) {
    avisarErro(e.message);
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
function adicionarPergunta(dados) {
  const bloco = document.createElement("fieldset");
  bloco.className = "pergunta";
  const titulo = document.createElement("legend");
  const tema = document.createElement("input");
  tema.placeholder = t("mesario.tema_pergunta");
  tema.required = true;
  tema.maxLength = 200;
  tema.value = dados?.tema ?? "";
  const opcoes = document.createElement("div");
  const remover = criarBotao(t("mesario.remover_pergunta"), () => { bloco.remove(); numerarPerguntas(); });
  remover.className = "remover-pergunta";
  bloco.append(titulo, tema, opcoes, criarBotao(t("mesario.mais_opcao"), () => adicionarOpcao(opcoes)), remover);
  const iniciais = dados?.opcoes ?? [
    { rotulo: t("mesario.opcao_padrao_1"), cor: "#dc2626" },
    { rotulo: t("mesario.opcao_padrao_2"), cor: "#2563eb" },
  ];
  for (const o of iniciais) adicionarOpcao(opcoes, o.rotulo, o.cor);
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

$("mais-pergunta").onclick = () => adicionarPergunta();

// Clonar: o formulário abre preenchido com a sessão escolhida (o questionário inteiro,
// se for um), com os temas já livres. O mesário edita o que quiser e cria — a sessão
// nova nasce zerada, e a antiga fica como está.
// Apagar de vez: some a votação e os votos dela. Fica o registro de quem apagou,
// com o tema e quantos votos foram embora, no log e na auditoria interna.
function apagarSessao(s) {
  const perguntas = s.total_perguntas > 1 ? s.total_perguntas : 0;
  return criarBotao(t("mesario.apagar_sessao"), async () => {
    const aviso = perguntas
      ? t("mesario.confirmar_apagar_questionario", { tema: s.tema, n: perguntas, votos: s.votos })
      : t("mesario.confirmar_apagar_sessao", { tema: s.tema, votos: s.votos });
    const sim = await confirmar({
      titulo: t("mesario.apagar_sessao"), acao: t("mesario.apagar_sessao"),
      texto: aviso, perigo: true, campo: { rotulo: t("mesario.digite_o_tema") }, digitar: s.tema,
    });
    if (sim === null) return;
    try {
      const r = await api("DELETE", `/api/admin/sessoes/${s.id}`);
      avisarFeito(t("mesario.sessao_apagada", r));
      await carregarSessoes();
    } catch (e) {
      avisarErro(e.message);
    }
  }, "perigo so-admin");
}

async function clonarSessao(s) {
  let modelo;
  try {
    modelo = await api("GET", `/api/admin/sessoes/${s.id}/modelo`);
  } catch (e) {
    return avisarErro(e.message);
  }
  $("perguntas").innerHTML = "";
  for (const pergunta of modelo.perguntas) adicionarPergunta(pergunta);
  $("nova-caso").value = modelo.caso;
  $("nova-celular").checked = modelo.celular;
  $("nova-peso-celular").value = modelo.peso_celular;
  $("nova-teste").checked = modelo.teste;
  mostrarAba("nova", true);
  $("perguntas").querySelector("input").focus();
}

$("nova-sessao").onsubmit = async (e) => {
  e.preventDefault();
  const perguntas = [];
  for (const bloco of $("perguntas").children) {
    const opcoes = [...bloco.querySelectorAll(".opcao")].map((linha) => {
      const [rotulo, cor] = linha.querySelectorAll("input");
      return { rotulo: rotulo.value.trim(), cor: cor.value };
    });
    const tema = bloco.querySelector("input").value.trim();
    if (opcoes.some((o) => !o.rotulo)) return avisarErro(t("mesario.preencha_opcoes", { tema }));
    if (new Set(opcoes.map((o) => o.rotulo.toLowerCase())).size !== opcoes.length) {
      return avisarErro(t("mesario.opcoes_repetidas", { tema }));
    }
    perguntas.push({ tema, opcoes });
  }
  const teste = $("nova-teste").checked;
  const celular = $("nova-celular").checked;
  const peso_celular = Number($("nova-peso-celular").value);
  const caso = $("nova-caso").value.trim();
  const criada = perguntas.length === 1
    ? await criarSessao({ ...perguntas[0], teste, celular, peso_celular, caso })
    : await criarSessao({ perguntas, teste, celular, peso_celular, caso }, "/api/admin/questionarios");
  if (criada) {
    reiniciarFormularioSessao();
    mostrarAba("sessoes");
  }
};

reiniciarFormularioSessao();

async function acao(caminho, metodo = "POST", corpo) {
  try {
    await api(metodo, caminho, corpo);
    await carregarSessoes();
  } catch (e) {
    avisarErro(e.message);
  }
}

async function zerar(s) {
  const confirmacao = await confirmar({
    titulo: t("mesario.zerar"), acao: t("mesario.zerar"), perigo: true,
    texto: t("mesario.confirmar_zerar", { tema: s.tema }),
    campo: { rotulo: t("mesario.digite_o_tema") }, digitar: s.tema,
  });
  if (confirmacao === null) return;
  try {
    const { apagados } = await api("POST", `/api/admin/sessoes/${s.id}/zerar`, { confirmacao });
    avisarFeito(t("mesario.votos_apagados", { n: apagados }));
    await carregarSessoes();
  } catch (e) {
    avisarErro(e.message);
  }
}

async function avancar(s) {
  const passo = PROXIMO[s.estado];
  const perigo = PERIGOSO.has(s.estado);
  const sim = await confirmar({
    titulo: t("mesario.confirmar_acao", { acao: passo.rotulo }),
    texto: `${s.tema}\n${passo.aviso}`,
    acao: passo.rotulo,
    perigo,
  });
  if (sim === null) return;
  try {
    await api("POST", `/api/admin/sessoes/${s.id}/avancar`);
  } catch (e) {
    const problemas = e.dados?.detail?.problemas;
    if (e.status === 409 && problemas) {
      const forcar = await confirmar({
        titulo: t("mesario.pendencias_titulo"),
        texto: problemas.join("\n"),
        acao: passo.rotulo,
        perigo: true,
      });
      if (forcar === null) return;
      await api("POST", `/api/admin/sessoes/${s.id}/avancar?forcar=true`);
    } else {
      avisarErro(e.message);
      return;
    }
  }
  await carregarSessoes();
}

// ---------- WebSocket ----------
// Reconectava em silêncio: o mesário ficava olhando um total parado achando que
// ninguém estava votando. A marca fica na faixa de estado até a conexão voltar.
function mostrarConexao(ligada) {
  $("sem-rede").hidden = ligada;
}

function conectarWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/mesario`);
  ws.onopen = () => {
    mostrarConexao(true);
    ws.send(JSON.stringify({ token: lerLogin()?.token }));
  };
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.tipo === "snapshot" || m.tipo === "estado") {
      mostrarEstado(m.sessao, m.total);
      carregarSessoes();
    }
    if (m.tipo === "total") $("total").textContent = m.total;
    if (m.tipo === "urnas" && window.mostrarUrnas) window.mostrarUrnas(m.urnas);
    if (m.tipo === "pedidos") mostrarPedidos(m.pedidos);
    if (m.cronometro) mostrarCronometro(m.cronometro);
    if (m.tipo === "cartao") carregarCartoes();
  };
  ws.onclose = (e) => {
    if (e.code === 4401) return sair();
    mostrarConexao(false);
    setTimeout(conectarWs, 2000);
  };
}

// ---------- Login ----------
function sair() {
  sessionStorage.removeItem("login");
  location.reload();
}

function iniciar() {
  const conta = lerLogin();
  // monitor só acompanha: o lugar dele é o monitoramento
  if (conta.papel === "monitor") return location.replace("/monitor/");
  document.body.dataset.papel = conta.papel;
  $("login").hidden = true;
  $("painel").hidden = false;
  mostrarSair(sair);
  api("GET", "/api/admin/presets")
    .then((p) => { presets = p; }, () => {})
    .finally(carregarSessoes);
  // a grade chega pelo WebSocket a cada 5s; busca já para não abrir vazia
  api("GET", "/api/admin/urnas").then((u) => window.mostrarUrnas(u), () => {});
  api("GET", "/api/admin/pedidos").then(mostrarPedidos, () => {});
  carregarCartoes().catch(() => {});
  if (conta.papel === "admin") carregarContas();
  conectarWs();
}

prepararLogin(iniciar);

if (lerLogin()) iniciar();


// ---------- Urnas ----------
// a grade é redesenhada a cada 5s: lembra quais menus de ações estavam abertos
const urnasComAcoesAbertas = new Set();

let idsDeUrnas = new Set();

window.mostrarUrnas = (urnas) => {
  idsDeUrnas = new Set(urnas.map((u) => u.id));
  const area = $("urnas");
  area.innerHTML = "";
  for (const u of urnas) {
    const classe = !u.ativa ? "inativa" : u.nunca_conectou ? "nunca" : u.online ? "online" : "offline";
    const situacao = !u.ativa ? t("mesario.desativada")
      : u.nunca_conectou ? t("mesario.nunca_conectou")
      : u.online ? t("mesario.n_pendentes", { n: u.pendentes })
      : t("mesario.offline_ha", { s: u.segundos_sem_sinal });

    const cartao = document.createElement("div");
    cartao.className = `urna ${classe}${u.teste ? " de-teste" : ""}`;
    const marcas = (u.reserva ? t("mesario.reserva_marca") : "") + (u.teste ? t("mesario.teste_marca") : "")
      + (u.peso !== 1 ? t("mesario.peso_marca", { n: u.peso }) : "");
    for (const texto of [`${u.id}${marcas}`, u.nome, t("mesario.n_votos", { n: u.votos_sessao }), situacao]) {
      const linha = document.createElement("div");
      linha.textContent = texto;
      cartao.appendChild(linha);
    }
    // offline a urna para de informar: vale o último número que ela mandou, porque é
    // ele que diz se compensa ir até lá buscar o arquivo exportado
    if (u.ativa && !u.online && !u.nunca_conectou && u.pendentes) {
      const presos = document.createElement("div");
      presos.className = "presos";
      presos.textContent = t(u.pendentes === 1 ? "mesario.um_preso" : "mesario.n_presos", { n: u.pendentes });
      cartao.appendChild(presos);
    }
    if (u.recusados) {
      const alerta = document.createElement("div");
      alerta.className = "recusados";
      alerta.textContent = t("mesario.n_recusados", { n: u.recusados });
      cartao.appendChild(alerta);
    }
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
    if (u.ativa) {
      acoes.appendChild(criarBotao(t("mesario.gerar_link"), async () => {
        const sim = await confirmar({
          titulo: t("mesario.gerar_link"), acao: t("mesario.gerar_link"), perigo: true,
          texto: t("mesario.confirmar_link", { id: u.id }),
        });
        if (sim === null) return;
        try {
          const { id, token } = await api("POST", `/api/admin/urnas/${u.id}/novo-token`);
          prepararLink(id, token);
        } catch (e) {
          avisarErro(e.message);
        }
      }, "perigo"));
      acoes.appendChild(criarBotao(t("mesario.mudar_peso", { n: u.peso }), async () => {
        const peso = await confirmar({
          titulo: t("mesario.mudar_peso", { n: u.peso }), acao: t("comum.salvar"),
          campo: { rotulo: t("mesario.pedir_peso", { id: u.id }), valor: u.peso, tipo: "number" },
        });
        if (peso === null) return;
        try {
          await api("POST", `/api/admin/urnas/${u.id}/peso`, { peso: Number(peso) });
          window.mostrarUrnas(await api("GET", "/api/admin/urnas"));
        } catch (e) {
          avisarErro(e.status === 422 ? t("mesario.peso_invalido") : e.message);
        }
      }));
      acoes.appendChild(criarBotao(t("mesario.desativar"), async () => {
        const sim = await confirmar({
          titulo: t("mesario.desativar"), acao: t("mesario.desativar"), perigo: true,
          texto: t("mesario.confirmar_desativar", { id: u.id }),
        });
        if (sim !== null) acao(`/api/admin/urnas/${u.id}/desativar`);
      }, "perigo"));
    }
    // urna com votos fica: a auditoria mostra o nome dela ao lado dos votos
    if (!u.votos_total) {
      acoes.appendChild(criarBotao(t("mesario.apagar_urna"), async () => {
        const sim = await confirmar({
          titulo: t("mesario.apagar_urna"), acao: t("mesario.apagar_urna"), perigo: true,
          texto: t("mesario.confirmar_apagar_urna", { id: u.id }),
        });
        if (sim === null) return;
        try {
          window.mostrarUrnas(await api("DELETE", `/api/admin/urnas/${u.id}`).then(
            () => api("GET", "/api/admin/urnas")));
        } catch (e) {
          avisarErro(e.message);
        }
      }, "perigo so-admin"));
    }
    area.appendChild(cartao);
  }
  if (!urnas.length) area.appendChild(vazio(t("mesario.sem_urnas")));
  testes.urnas = urnas.filter((u) => u.teste).length;
  mostrarLimparTestes();
};

$("nova-urna").onsubmit = async (e) => {
  e.preventDefault();
  try {
    const { id, token } = await api("POST", "/api/admin/urnas", {
      id: $("nova-id").value,
      nome: $("nova-nome").value,
      reserva: $("nova-reserva").checked,
      teste: $("nova-urna-teste").checked,
      peso: Number($("nova-peso").value),
    });
    prepararLink(id, token);
    e.target.reset();
  } catch (err) {
    avisarErro(err.message);
  }
};

// ---------- Pedidos de cadastro de urna ----------
// a lista chega a cada 5s: as linhas já desenhadas ficam, para não apagar o que o mesário digita
function mostrarPedidos(pedidos) {
  const lista = $("lista-pedidos");
  const codigos = new Set(pedidos.map((p) => p.codigo));
  for (const linha of [...lista.children]) if (!codigos.has(linha.dataset.codigo)) linha.remove();
  const desenhados = new Set([...lista.children].map((l) => l.dataset.codigo));
  for (const p of pedidos) if (!desenhados.has(p.codigo)) lista.appendChild(linhaPedido(p));
  $("pedidos").hidden = !pedidos.length;
  marcarPedidosNaAba(pedidos.length);
}

// O pedido só aparecia dentro da aba Urnas: quem estava em Sessões não via nada e a
// urna ficava esperando na tela, com o código à mostra, sem ninguém aprovar.
function marcarPedidosNaAba(n) {
  const aba = document.querySelector('[data-aba="urnas"]');
  let marca = aba.querySelector(".contador");
  if (!n) {
    marca?.remove();
    return aba.removeAttribute("aria-label");
  }
  if (!marca) {
    marca = document.createElement("span");
    marca.className = "contador";
    aba.appendChild(marca);
  }
  marca.textContent = n;
  aba.setAttribute("aria-label", t("mesario.aba_urnas_pedidos", { n }));
}

// primeiro "urnaN" livre, contando também os sugeridos nos outros pedidos abertos
function sugerirUrna() {
  const usados = new Set([...idsDeUrnas, ...[...document.querySelectorAll(".pedido .id-urna")].map((c) => c.value)]);
  let n = 1;
  while (usados.has(`urna${n}`)) n++;
  return n;
}

function campo(tipo, rotulo, valor) {
  const c = document.createElement("input");
  c.type = tipo;
  c.setAttribute("aria-label", rotulo);
  if (tipo === "checkbox") c.checked = valor;
  else c.value = valor;
  return c;
}

function linhaPedido(p) {
  const n = sugerirUrna();
  const linha = document.createElement("form");
  linha.className = "pedido";
  linha.dataset.codigo = p.codigo;
  const codigo = document.createElement("span");
  codigo.className = "codigo";
  codigo.textContent = p.codigo;
  const id = campo("text", t("mesario.id_rotulo"), `urna${n}`);
  id.className = "id-urna";
  id.required = true;
  id.pattern = "[a-z0-9-]{1,30}";
  const nome = campo("text", t("mesario.nome_rotulo"), t("mesario.nome_sugerido", { n }));
  nome.required = true;
  const reserva = campo("checkbox", t("mesario.reserva"), false);
  const teste = campo("checkbox", t("mesario.urna_teste"), false);
  const peso = campo("number", t("mesario.peso"), 1);
  Object.assign(peso, { min: 1, max: 10, className: "peso-urna" });
  const rotulado = (caixa, texto) => {
    const l = document.createElement("label");
    l.append(caixa, ` ${texto}`);
    return l;
  };
  const aprovar = criarBotao(t("mesario.aprovar"), null, "principal");
  aprovar.type = "submit";
  const recusar = criarBotao(t("mesario.recusar"), async () => {
    try {
      await api("DELETE", `/api/admin/pedidos/${p.codigo}`);
      linha.remove();
      $("pedidos").hidden = !$("lista-pedidos").children.length;
    } catch (e) {
      avisarErro(e.message);
    }
  }, "perigo");
  linha.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("POST", `/api/admin/pedidos/${p.codigo}/aprovar`, {
        id: id.value, nome: nome.value, reserva: reserva.checked, teste: teste.checked, peso: Number(peso.value),
      });
      linha.remove();
      $("pedidos").hidden = !$("lista-pedidos").children.length;
      window.mostrarUrnas(await api("GET", "/api/admin/urnas"));
    } catch (err) {
      avisarErro(err.message);
    }
  };
  const comPeso = document.createElement("label");
  comPeso.className = "peso";
  comPeso.append(t("mesario.peso"), peso);
  linha.append(codigo, id, nome, rotulado(reserva, t("mesario.reserva")), rotulado(teste, t("mesario.urna_teste")),
    comPeso, aprovar, recusar);
  return linha;
}

// ---------- Registro ----------
// A auditoria interna inteira: sessões, urnas, cartões e contas, com quem fez cada
// coisa. O 'por' é posto pelo servidor em cada evento; o resto do detalhe vira texto.
function celulaRegistro(texto, classe) {
  const td = document.createElement("td");
  td.textContent = texto;
  if (classe) td.className = classe;
  return td;
}

function campos(detalhe) {
  return Object.fromEntries(detalhe.split(" ").filter((p) => p.includes("=")).map((p) => p.split(/=(.*)/)));
}

// O registro guarda tudo o que já foi feito e só crescia: depois de alguns júris
// eram centenas de linhas de uma vez, sem busca e sem fim. Agora vem de 50 em 50,
// e a busca passa por tudo o que a linha mostra — o que foi, o detalhe e quem fez.
const PAGINA_REGISTRO = 50;
let eventosDoRegistro = [];
let visiveisNoRegistro = PAGINA_REGISTRO;

// o detalhe cru ("sessao=3 votos=12") vira texto legível, e é por ele que a busca
// passa: procurar pelo que está escrito na tela é o que a pessoa espera
function detalheDoRegistro(e) {
  const { por, ...resto } = campos(e.detalhe);
  return { por, texto: Object.entries(resto).map(([c, v]) => `${c}: ${v}`).join(" · ") };
}

function linhaDoRegistro(e) {
  const { por, texto } = detalheDoRegistro(e);
  const linha = document.createElement("tr");
  linha.append(
    celulaRegistro(new Date(e.em).toLocaleString(document.documentElement.lang), "quando"),
    celulaRegistro(t(`registro.${e.tipo}`)),
    celulaRegistro(texto, "detalhe"),
    celulaRegistro(por ?? "—", "quem"),
  );
  return linha;
}

function linhaVaziaDoRegistro(texto) {
  const linha = document.createElement("tr");
  const celula = celulaRegistro(texto, "vazio");
  celula.colSpan = 4;
  linha.appendChild(celula);
  return linha;
}

function procurado(e, termo) {
  const { por, texto } = detalheDoRegistro(e);
  return `${t(`registro.${e.tipo}`)} ${texto} ${por ?? ""}`.toLowerCase().includes(termo);
}

function desenharRegistro() {
  const termo = $("busca-registro").value.trim().toLowerCase();
  const achados = termo ? eventosDoRegistro.filter((e) => procurado(e, termo)) : eventosDoRegistro;
  const mostrados = achados.slice(0, visiveisNoRegistro);
  $("lista-registro").replaceChildren(...(mostrados.length
    ? mostrados.map(linhaDoRegistro)
    : [linhaVaziaDoRegistro(t(termo ? "registro.nada_encontrado" : "registro.sem_eventos"))]));
  $("conta-registro").textContent = achados.length
    ? t("registro.contagem", { n: mostrados.length, total: achados.length })
    : "";
  $("mais-registro").hidden = mostrados.length >= achados.length;
}

async function carregarRegistro() {
  try {
    eventosDoRegistro = (await api("GET", "/api/admin/eventos")).reverse();
  } catch (e) {
    return avisarErro(e.message);
  }
  visiveisNoRegistro = PAGINA_REGISTRO;
  desenharRegistro();
}

$("busca-registro").setAttribute("aria-label", t("registro.buscar"));
$("busca-registro").oninput = () => {
  visiveisNoRegistro = PAGINA_REGISTRO;
  desenharRegistro();
};
$("mais-registro").onclick = () => {
  visiveisNoRegistro += PAGINA_REGISTRO;
  desenharRegistro();
};

// ---------- Contas ----------
const PAPEIS = ["admin", "mesario", "monitor"];

async function alterarConta(usuario, mudanca) {
  try {
    await api("PATCH", `/api/admin/contas/${usuario}`, mudanca);
  } catch (e) {
    avisarErro(e.message);
  }
  carregarContas();
}

async function carregarContas() {
  const contas = await api("GET", "/api/admin/contas");
  const eu = lerLogin().usuario;
  $("lista-contas").replaceChildren(...contas.map((c) => {
    const linha = document.createElement("tr");
    if (!c.ativa) linha.className = "inativa";
    const celula = (conteudo) => {
      const td = document.createElement("td");
      td.append(conteudo);
      linha.appendChild(td);
      return td;
    };
    celula(c.usuario + (c.usuario === eu ? t("mesario.voce") : ""));
    celula(c.nome);
    const papel = document.createElement("select");
    papel.setAttribute("aria-label", t("mesario.papel"));
    for (const p of PAPEIS) papel.add(new Option(t(`papel.${p}`), p, false, p === c.papel));
    papel.disabled = c.usuario === eu;
    papel.onchange = () => alterarConta(c.usuario, { papel: papel.value });
    celula(papel);
    const acoes = celula("");
    if (c.usuario !== eu) {
      acoes.append(criarBotao(t("mesario.redefinir_senha"), async () => {
        const nova = await confirmar({
          titulo: t("mesario.redefinir_senha"), acao: t("comum.salvar"),
          campo: { rotulo: t("mesario.pedir_nova_senha", { usuario: c.usuario }) },
        });
        if (nova === null) return;
        try {
          await api("POST", `/api/admin/contas/${c.usuario}/senha`, { nova });
          avisarFeito(t("mesario.senha_redefinida", { usuario: c.usuario }));
        } catch (e) {
          avisarErro(e.status === 422 ? t("mesario.senha_curta") : e.message);
        }
      }), " ", c.ativa
        ? criarBotao(t("mesario.desativar"), async () => {
          const sim = await confirmar({
            titulo: t("mesario.desativar"), acao: t("mesario.desativar"), perigo: true,
            texto: t("mesario.confirmar_desativar_conta", { usuario: c.usuario }),
          });
          if (sim !== null) alterarConta(c.usuario, { ativa: false });
        }, "perigo")
        : criarBotao(t("mesario.reativar"), () => alterarConta(c.usuario, { ativa: true })));
    }
    return linha;
  }));
}

$("nova-conta").onsubmit = async (e) => {
  e.preventDefault();
  try {
    await api("POST", "/api/admin/contas", {
      usuario: $("conta-usuario").value.trim().toLowerCase(),
      nome: $("conta-nome").value,
      papel: $("conta-papel").value,
      senha: $("conta-senha").value,
    });
    e.target.reset();
    carregarContas();
  } catch (err) {
    avisarErro(err.message);
  }
};

$("minha-senha").onsubmit = async (e) => {
  e.preventDefault();
  try {
    await api("POST", "/api/eu/senha", { atual: $("senha-atual").value, nova: $("senha-nova").value });
    e.target.reset();
    avisarFeito(t("mesario.senha_trocada"));
  } catch (err) {
    avisarErro(err.message);
  }
};

// ---------- Cartões do telão ----------
let editando = null;
let cartoesCarregados = [];

async function carregarCartoes() {
  mostrarCartoes(await api("GET", "/api/admin/cartoes"));
}

function mostrarCartoes(cartoes) {
  cartoesCarregados = cartoes;
  atualizarCasos();
  if (casoFiltro) cartoes = cartoes.filter((c) => c.pasta === casoFiltro);
  const pastas = [...new Set(cartoes.map((c) => c.pasta))];
  $("pastas").replaceChildren(...pastas.map((p) => new Option(p)));
  $("ocultar-cartao").hidden = !cartoes.some((c) => c.no_telao);
  const lista = $("lista-cartoes");
  lista.innerHTML = "";
  if (!cartoes.length) return lista.appendChild(vazio(t("mesario.sem_cartoes")));
  for (const pasta of pastas) {
    const bloco = document.createElement("div");
    bloco.className = "cartao";
    const nome = document.createElement("h2");
    nome.textContent = pasta;
    bloco.appendChild(nome);
    for (const c of cartoes.filter((x) => x.pasta === pasta)) bloco.appendChild(linhaCartao(c));
    lista.appendChild(bloco);
  }
}

function linhaCartao(c) {
  const linha = document.createElement("div");
  linha.className = "sessao" + (c.no_telao ? " ativa" : "");
  const titulo = document.createElement("div");
  titulo.className = "titulo";
  titulo.textContent = c.titulo;
  if (c.no_telao) {
    const selo = document.createElement("span");
    selo.className = "selo celular";
    selo.textContent = t("mesario.no_telao");
    titulo.appendChild(selo);
  }
  linha.append(
    titulo,
    criarBotao(t("mesario.exibir"), () => comandarCartao("POST", `/${c.id}/exibir`), "principal"),
    criarBotao(t("mesario.editar_cartao"), () => editarCartao(c)),
    criarBotao(t("mesario.apagar"), async () => {
      const sim = await confirmar({
        titulo: t("mesario.apagar"), acao: t("mesario.apagar"), perigo: true,
        texto: t("mesario.confirmar_apagar_cartao", { titulo: c.titulo }),
      });
      if (sim !== null) comandarCartao("DELETE", `/${c.id}`);
    }, "perigo"),
  );
  return linha;
}

async function comandarCartao(metodo, caminho, corpo) {
  try {
    await api(metodo, `/api/admin/cartoes${caminho}`, corpo);
    await carregarCartoes();
    return true;
  } catch (e) {
    avisarErro(e.message);
    return false;
  }
}

function editarCartao(c) {
  editando = c.id;
  $("form-cartao-titulo").textContent = t("mesario.editando_cartao");
  $("cancelar-cartao").hidden = false;
  $("cartao-pasta").value = c.pasta;
  $("cartao-titulo").value = c.titulo;
  $("cartao-texto").value = c.texto;
  $("cartao-link").value = c.fonte;
  $("cartao-pasta").scrollIntoView({ block: "center" });
}

function limparFormCartao() {
  editando = null;
  $("form-cartao").reset();
  $("form-cartao-titulo").textContent = t("mesario.novo_cartao");
  $("cancelar-cartao").hidden = true;
}

$("cancelar-cartao").onclick = limparFormCartao;
$("ocultar-cartao").onclick = () => comandarCartao("POST", "/ocultar");

$("form-cartao").onsubmit = async (e) => {
  e.preventDefault();
  const dados = {
    pasta: $("cartao-pasta").value,
    titulo: $("cartao-titulo").value,
    texto: $("cartao-texto").value,
    fonte: $("cartao-link").value,
  };
  const salvo = editando
    ? await comandarCartao("PATCH", `/${editando}`, dados)
    : await comandarCartao("POST", "", dados);
  if (salvo) limparFormCartao();
};

// o texto vem do servidor, que baixa a página: o mesário confere e corrige antes de salvar
$("trazer-link").onclick = async () => {
  const url = $("cartao-link").value.trim();
  if (!url) return;
  const botao = $("trazer-link");
  botao.disabled = true;
  botao.textContent = t("mesario.buscando");
  try {
    const noticia = await api("POST", "/api/admin/cartoes/importar", { url });
    $("cartao-titulo").value = noticia.titulo;
    $("cartao-texto").value = noticia.texto;
  } catch (e) {
    avisarErro(e.message);
  } finally {
    botao.disabled = false;
    botao.textContent = t("mesario.trazer_link");
  }
};

// ---------- Cronômetro das falas ----------
// mesma contagem local do telão: o servidor manda quanto falta, a tela tica sozinha
let cronometro = { visivel: false };
let tiqueCronometro = null;

function mostrarCronometro(c) {
  cronometro = { ...c, recebido: performance.now() };
  $("crono-ativo").hidden = !c.visivel;
  $("crono-nome").textContent = c.titulo;
  $("crono-pausar").textContent = t(c.rodando ? "mesario.pausar" : "mesario.retomar");
  desenharCronometro();
  clearInterval(tiqueCronometro);
  if (c.visivel && c.rodando) tiqueCronometro = setInterval(desenharCronometro, 250);
}

function desenharCronometro() {
  const c = cronometro;
  if (!c.visivel) return;
  const restante = c.rodando ? c.restante - (performance.now() - c.recebido) / 1000 : c.restante;
  const s = restante >= 0 ? Math.ceil(restante) : Math.floor(-restante);
  $("crono-tempo").textContent = `${restante < 0 ? "+" : ""}${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  $("crono-tempo").parentElement.classList.toggle("esgotado", restante < 0);
}

async function comandarCronometro(metodo, caminho, corpo) {
  try {
    mostrarCronometro(await api(metodo, `/api/admin/cronometro${caminho}`, corpo));
  } catch (e) {
    avisarErro(e.message);
  }
}

// As quatro etapas do roteiro do júri, prontas num clique; o resto das falas continua
// sendo título e minutos digitados.
const ETAPAS = [
  { titulo: "mesario.etapa.denuncia", minutos: 5 },
  { titulo: "mesario.etapa.pericia", minutos: 20 },
  { titulo: "mesario.etapa.debates", minutos: 20 },
  { titulo: "mesario.etapa.votacao", minutos: 10 },
];

async function iniciarEtapa(titulo, minutos) {
  // trocar uma contagem em andamento por engano custa caro no meio da sessão
  if (cronometro.visivel && cronometro.rodando) {
    const sim = await confirmar({
      titulo: t("mesario.trocar_contagem"), acao: t("mesario.trocar_contagem"), perigo: true,
      texto: t("mesario.confirmar_trocar_cronometro", { titulo }),
    });
    if (sim === null) return;
  }
  $("crono-titulo").value = titulo;
  $("crono-minutos").value = minutos;
  comandarCronometro("POST", "", { titulo, minutos });
}

$("etapas").replaceChildren(...ETAPAS.map(({ titulo, minutos }) => criarBotao(
  t("mesario.etapa_botao", { nome: t(titulo), n: minutos }),
  () => iniciarEtapa(t(titulo), minutos))));

$("form-cronometro").onsubmit = (e) => {
  e.preventDefault();
  comandarCronometro("POST", "", { titulo: $("crono-titulo").value, minutos: Number($("crono-minutos").value) });
};
$("crono-pausar").onclick = () => comandarCronometro("POST", cronometro.rodando ? "/pausar" : "/retomar");
$("crono-mais").onclick = () => comandarCronometro("POST", "/ajustar", { segundos: 60 });
$("crono-menos").onclick = () => comandarCronometro("POST", "/ajustar", { segundos: -60 });
$("crono-encerrar").onclick = () => comandarCronometro("DELETE", "");

// ---------- Telão ----------
$("abrir-telao").onclick = async () => {
  // abre a aba antes do await para o navegador não bloquear o pop-up
  const aba = window.open("about:blank", "_blank");
  try {
    const { chave } = await api("GET", "/api/admin/telao");
    aba.location = `/telao/#chave=${encodeURIComponent(chave)}`;
  } catch (e) {
    aba.close();
    avisarErro(e.message);
  }
};

// ---------- Importar fila ----------
const MOTIVOS = ["sessao_encerrada", "sessao_nao_aberta", "sessao_inexistente", "opcao_invalida", "urna_de_teste"];

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
  const sim = await confirmar({
    titulo: t("mesario.importar_votos"), acao: t("mesario.importar_votos"),
    texto: t("mesario.confirmar_importar", { n: dados.votos.length, urna: dados.urna_id }),
  });
  if (sim === null) return;

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