const $ = (id) => document.getElementById(id);

// horários vêm em UTC (ISO); mostra no fuso de quem consulta
const hora = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR") : "—");

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

async function listar() {
  const sessoes = await (await fetch("/api/auditoria/sessoes")).json();
  const area = $("sessoes");
  area.innerHTML = "";
  if (!sessoes.length) {
    area.innerHTML = "<p>Nenhuma sessão revelada ainda.</p>";
    return;
  }
  for (const s of sessoes) {
    const a = document.createElement("a");
    a.href = `#${s.id}`;
    a.textContent = s.tema;
    area.appendChild(a);
  }
  mostrar();
}

async function mostrar() {
  const sid = location.hash.slice(1);
  document.querySelectorAll("#sessoes a").forEach((a) => a.classList.toggle("atual", a.hash === `#${sid}`));
  if (!sid) return;
  const r = await fetch(`/api/auditoria/sessoes/${encodeURIComponent(sid)}`);
  if (!r.ok) {
    $("detalhe").hidden = true;
    return;
  }
  const a = await r.json();
  $("tema").textContent = a.tema;
  $("total").textContent = a.total;

  const soma = a.total || 1;
  $("resultado").innerHTML = "";
  for (const o of a.resultado) {
    const barra = document.createElement("div");
    barra.className = "barra";
    const rotulo = document.createElement("span");
    rotulo.textContent = o.rotulo;
    const trilho = document.createElement("div");
    trilho.className = "trilho";
    const preenchimento = document.createElement("div");
    preenchimento.style.width = `${(o.votos / soma) * 100}%`;
    preenchimento.style.background = o.cor;
    trilho.appendChild(preenchimento);
    const numero = document.createElement("strong");
    numero.textContent = o.votos;
    barra.append(rotulo, trilho, numero);
    $("resultado").appendChild(barra);
  }

  $("urnas").replaceChildren(...a.por_urna.map((u) =>
    linha(celula(u.urna), celula(u.votos, "num"), celula(hora(u.primeiro_voto)), celula(hora(u.ultimo_voto)))));
  $("eventos").replaceChildren(...a.eventos.map((e) => linha(celula(hora(e.em)), celula(e.evento))));
  $("detalhe").hidden = false;
}

addEventListener("hashchange", mostrar);
listar();
