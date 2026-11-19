const $ = (id) => document.getElementById(id);

// horários vêm em UTC (ISO); mostra no fuso de quem consulta
const hora = (iso) => (iso ? new Date(iso).toLocaleString(document.documentElement.lang) : "—");
const dia = (iso) => (iso ? new Date(iso).toLocaleDateString(document.documentElement.lang) : "");

// A auditoria é pública, mas quem operou cada passo interessa à mesa, não à rua: o
// servidor só manda o "por" para quem entrou com conta, e a coluna acompanha.
const comConta = () => (typeof lerLogin === "function" ? lerLogin() : null);

const rotulo = (s) => (s.total_perguntas > 1
  ? `${t("comum.pergunta_de", { n: s.pergunta, total: s.total_perguntas })} · ${s.tema}`
  : s.tema);

function celula(texto, classe) {
  const td = document.createElement("td");
  td.textContent = texto;
  if (classe) td.className = classe;
  return td;
}

function linha(...celulas) {
  const tr = document.createElement("tr");
  tr.append(...celulas);
  return tr;
}

// um bloco por caso, e dentro dele as perguntas de cada questionário na ordem
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

function linkDaSessao(s, noQuestionario) {
  const a = document.createElement("a");
  a.href = `#${s.id}`;
  const nome = document.createElement("span");
  nome.textContent = noQuestionario ? `${s.pergunta}. ${s.tema}` : s.tema;
  const quando = document.createElement("small");
  quando.textContent = dia(s.encerrada_em);
  a.append(nome, quando);
  return a;
}

function blocoDoCaso({ caso, grupos }) {
  const bloco = document.createElement("div");
  bloco.className = "caso";
  const nome = document.createElement("h3");
  nome.textContent = caso || t("auditoria.sem_caso");
  bloco.appendChild(nome);
  for (const grupo of grupos) {
    grupo.sort((a, b) => a.pergunta - b.pergunta);
    for (const s of grupo) bloco.appendChild(linkDaSessao(s, grupo.length > 1));
  }
  return bloco;
}

async function listar() {
  const sessoes = await (await fetch("/api/auditoria/sessoes")).json();
  const area = $("sessoes");
  area.innerHTML = "";
  if (!sessoes.length) {
    const aviso = document.createElement("p");
    aviso.textContent = t("auditoria.nenhuma");
    area.appendChild(aviso);
    $("escolha").hidden = true;
    return;
  }
  area.replaceChildren(...porCaso(sessoes).map(blocoDoCaso));
  mostrar();
}

async function mostrar() {
  const sid = location.hash.slice(1);
  document.querySelectorAll("#sessoes a").forEach((a) => a.classList.toggle("atual", a.hash === `#${sid}`));
  $("escolha").hidden = Boolean(sid);
  if (!sid) return;
  const r = await fetch(`/api/auditoria/sessoes/${encodeURIComponent(sid)}`,
                        comConta() ? { headers: autorizacao() } : undefined);
  if (!r.ok) {
    $("detalhe").hidden = true;
    $("escolha").hidden = false;
    return;
  }
  const a = await r.json();
  $("caso-detalhe").textContent = a.caso ?? "";
  $("tema").textContent = rotulo(a);
  $("total").textContent = a.total;

  // barras pelos pontos (soma dos pesos); com pesos diferentes, o número de votos embaixo
  const soma = a.resultado.reduce((s, o) => s + o.pontos, 0) || 1;
  const ponderado = a.resultado.some((o) => o.pontos !== o.votos);
  $("resultado").innerHTML = "";
  for (const o of a.resultado) {
    const barra = document.createElement("div");
    barra.className = "barra";
    const rotulo = document.createElement("span");
    rotulo.textContent = o.rotulo;
    const trilho = document.createElement("div");
    trilho.className = "trilho";
    const preenchimento = document.createElement("div");
    preenchimento.style.width = `${(o.pontos / soma) * 100}%`;
    preenchimento.style.background = o.cor;
    trilho.appendChild(preenchimento);
    const numero = document.createElement("div");
    numero.className = "numero";
    const pontos = document.createElement("strong");
    pontos.textContent = o.pontos;
    numero.appendChild(pontos);
    if (ponderado) {
      const votos = document.createElement("small");
      votos.textContent = t("comum.pontos_e_votos", { n: o.votos });
      numero.appendChild(votos);
    }
    barra.append(rotulo, trilho, numero);
    $("resultado").appendChild(barra);
  }

  $("urnas").replaceChildren(...a.por_urna.map((u) =>
    linha(celula(u.urna), celula(u.votos, "num"), celula(u.peso, "num"), celula(u.pontos, "num"),
      celula(hora(u.primeiro_voto)), celula(hora(u.ultimo_voto)))));
  // sem login o servidor não manda o autor, e a coluna sai da tabela
  const comAutor = a.eventos.some((e) => "por" in e);
  $("col-quem").hidden = !comAutor;
  $("eventos").replaceChildren(...a.eventos.map((e) => linha(
    celula(hora(e.em)), celula(e.evento),
    ...(comAutor ? [celula(e.por || "—", "quem")] : []))));
  $("detalhe").hidden = false;
}

addEventListener("hashchange", mostrar);
if (comConta()) mostrarSair(() => location.reload());
listar();
