// Login do mesário, comum ao painel e ao monitoramento: mostrar a senha, aviso
// de Caps Lock, tentativas restantes, contagem do bloqueio e botão Sair.
//
// prepararLogin(verificar, aoEntrar): verificar(senha) faz uma chamada autenticada
// e devolve a Response; aoEntrar() roda quando a senha confere.
// mostrarSair(aoSair): põe o botão Sair no cabeçalho.

const AVISAR_COM = 3; // avisa das tentativas restantes só quando o bloqueio está perto

function formatarEspera(segundos) {
  const m = Math.floor(segundos / 60);
  const s = String(segundos % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function prepararLogin(verificar, aoEntrar) {
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
      r = await verificar(campo.value);
    } catch {
      erro.textContent = t("login.sem_conexao");
      return;
    } finally {
      entrar.textContent = rotulo;
      entrar.disabled = false;
    }
    if (r.ok) {
      sessionStorage.setItem("senha", campo.value);
      campo.value = "";
      return aoEntrar();
    }
    const espera = Number(r.headers.get("Retry-After"));
    if (r.status === 429 || espera) return bloquear(espera || 60);
    const restantes = Number(r.headers.get("X-Tentativas-Restantes"));
    erro.textContent = r.headers.has("X-Tentativas-Restantes") && restantes <= AVISAR_COM
      ? t("login.restantes", { n: restantes })
      : t("comum.senha_incorreta");
    campo.select();
  };
  campo.focus();
}

function mostrarSair(aoSair) {
  const b = document.createElement("button");
  b.type = "button";
  b.id = "sair";
  b.textContent = t("comum.sair");
  b.onclick = aoSair;
  document.querySelector(".topo .acoes").appendChild(b);
}
