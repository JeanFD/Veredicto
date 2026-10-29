// Login do painel e do monitoramento: usuário e senha, mostrar a senha, aviso de
// Caps Lock, tentativas restantes, contagem do bloqueio e botão Sair.
//
// prepararLogin(aoEntrar): o formulário manda usuário e senha para /api/login; o
// token (válido por 12 horas) fica no sessionStorage da aba, nunca a senha. Fechar a
// aba ou clicar em Sair encerra o acesso. aoEntrar(conta) roda quando o login confere.
// lerLogin(): { token, usuario, nome, papel } ou null. autorizacao(): o cabeçalho.
// mostrarSair(aoSair): põe o nome da conta e o botão Sair no cabeçalho.

const AVISAR_COM = 3; // avisa das tentativas restantes só quando o bloqueio está perto

function lerLogin() {
  try {
    const login = JSON.parse(sessionStorage.getItem("login"));
    return login && login.expira_em * 1000 > Date.now() ? login : null;
  } catch {
    return null;
  }
}

const autorizacao = () => ({ Authorization: `Bearer ${lerLogin()?.token}` });

async function sairDaConta() {
  const login = lerLogin();
  sessionStorage.removeItem("login");
  if (login) await fetch("/api/logout", { method: "POST", headers: { Authorization: `Bearer ${login.token}` } }).catch(() => {});
}

function formatarEspera(segundos) {
  const m = Math.floor(segundos / 60);
  const s = String(segundos % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function prepararLogin(aoEntrar) {
  const usuario = document.getElementById("usuario");
  const campo = document.getElementById("senha");
  const erro = document.getElementById("erro-login");
  const entrar = document.getElementById("entrar");
  const caps = document.getElementById("caps");
  const ver = document.getElementById("ver-senha");
  let contagem = null;

  ver.onclick = () => {
    const visivel = campo.type === "password";
    campo.type = visivel ? "text" : "password";
    ver.setAttribute("aria-pressed", visivel);
    ver.setAttribute("aria-label", t(visivel ? "login.ocultar" : "login.mostrar"));
    ver.title = ver.getAttribute("aria-label");
    campo.focus();
  };
  ver.setAttribute("aria-label", t("login.mostrar"));
  ver.title = t("login.mostrar");

  const conferirCaps = (e) => {
    if (e.getModifierState) caps.hidden = !e.getModifierState("CapsLock");
  };
  campo.addEventListener("keydown", conferirCaps);
  campo.addEventListener("keyup", conferirCaps);
  campo.addEventListener("blur", () => { caps.hidden = true; });

  function bloquear(segundos) {
    clearInterval(contagem);
    entrar.disabled = true;
    const fim = Date.now() + segundos * 1000;
    const atualizar = () => {
      const faltam = Math.max(0, Math.ceil((fim - Date.now()) / 1000));
      erro.textContent = t("login.bloqueado", { tempo: formatarEspera(faltam) });
      if (!faltam) {
        clearInterval(contagem);
        entrar.disabled = false;
        erro.textContent = "";
      }
    };
    atualizar();
    contagem = setInterval(atualizar, 1000);
  }

  document.getElementById("form-login").onsubmit = async (e) => {
    e.preventDefault();
    erro.textContent = "";
    entrar.disabled = true;
    const rotulo = entrar.textContent;
    entrar.textContent = t("login.entrando");
    let r;
    try {
      r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ usuario: usuario.value.trim(), senha: campo.value }),
      });
    } catch {
      erro.textContent = t("login.sem_conexao");
      return;
    } finally {
      entrar.textContent = rotulo;
      entrar.disabled = false;
    }
    if (r.ok) {
      const conta = await r.json();
      sessionStorage.setItem("login", JSON.stringify(conta));
      campo.value = "";
      return aoEntrar(conta);
    }
    const espera = Number(r.headers.get("Retry-After"));
    if (r.status === 429 || espera) return bloquear(espera || 60);
    const restantes = Number(r.headers.get("X-Tentativas-Restantes"));
    erro.textContent = r.headers.has("X-Tentativas-Restantes") && restantes <= AVISAR_COM
      ? t("login.restantes", { n: restantes })
      : t("login.incorreto");
    campo.select();
  };
  (usuario.value ? campo : usuario).focus();
}

function mostrarSair(aoSair) {
  const conta = lerLogin();
  const acoes = document.querySelector(".topo .acoes");
  if (conta) {
    const quem = document.createElement("span");
    quem.id = "conta-atual";
    quem.className = "conta-atual";
    quem.textContent = `${conta.nome} · ${t(`papel.${conta.papel}`)}`;
    acoes.appendChild(quem);
  }
  const b = document.createElement("button");
  b.type = "button";
  b.id = "sair";
  b.textContent = t("comum.sair");
  b.onclick = async () => {
    await sairDaConta();
    aoSair();
  };
  acoes.appendChild(b);
}
