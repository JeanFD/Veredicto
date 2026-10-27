// Tradução das telas (português e inglês), sem biblioteca.
//
// - Idioma: o escolhido no seletor PT/EN (guardado no aparelho) ou, sem escolha,
//   o do navegador: inglês se ele estiver em inglês, português nos demais casos.
// - HTML: elementos com data-i18n recebem o texto; data-i18n-placeholder, o placeholder.
// - JS: t("chave", { variavel }) devolve o texto com {variavel} preenchida.
// - Servidor: todo fetch leva Accept-Language, e as mensagens de erro voltam no mesmo idioma.
// Tema e opções de uma sessão são conteúdo do mesário e não são traduzidos.
// tests/test_i18n.py confere que pt e en têm as mesmas chaves e que toda chave usada existe.
const TEXTOS = /* textos:inicio */ {
  "pt": {
    "comum.carregando": "Carregando…",
    "comum.confirmar": "Confirmar",
    "comum.corrigir": "Corrigir",
    "comum.confirmar_voto": "Confirmar voto em {opcao}?",
    "comum.enviando": "Enviando voto…",
    "comum.voto_registrado": "Voto registrado",
    "comum.pergunta_de": "Pergunta {n} de {total}",
    "comum.senha": "Senha",
    "comum.entrar": "Entrar",
    "comum.senha_incorreta": "Senha incorreta",
    "comum.trocar_idioma": "Mudar para inglês",

    "estado.AGUARDANDO": "AGUARDANDO",
    "estado.ABERTA": "ABERTA",
    "estado.ENCERRADA": "ENCERRADA",
    "estado.REVELADA": "REVELADA",

    "urna.titulo": "Veredicto · Urna",
    "urna.nao_configurada": "Urna não configurada",
    "urna.fechada": "Votação fechada",
    "urna.aguarde_proxima": "Aguarde a próxima pergunta",
    "urna.sem_conexao": "Sem conexão: voto guardado, será enviado quando a rede voltar",
    "urna.recusa.sessao_encerrada": "Voto NÃO computado: a votação já foi encerrada",
    "urna.recusa.sessao_nao_aberta": "Voto NÃO computado: a votação ainda não foi aberta",
    "urna.recusa.outra": "Voto NÃO computado: o servidor recusou o voto",
    "urna.chame_mesario": "{motivo}. Chame o mesário.",
    "urna.entendi": "Entendi",
    "urna.nao_autorizada": "urna não autorizada",
    "urna.online": "online",
    "urna.offline": "offline",
    "urna.exportar": "exportar fila ({n})",

    "telao.titulo": "Veredito · Telão",
    "telao.aguardando": "Aguardando",
    "telao.legenda.AGUARDANDO": "votação ainda não aberta",
    "telao.legenda.ABERTA": "votos registrados",
    "telao.legenda.ENCERRADA": "votação encerrada · aguardando revelação",
    "telao.vote_celular": "Vote pelo celular",

    "celular.titulo": "Veredicto · Voto pelo celular",
    "celular.escaneie": "Escaneie o QR code exibido no telão.",
    "celular.nao_entrou": "Não foi possível entrar na votação.",
    "celular.encerrada": "Voto NÃO computado: a votação já foi encerrada.",
    "celular.nao_computado": "Voto NÃO computado. Tente de novo.",
    "celular.sem_conexao": "Sem conexão com o servidor.",
    "celular.tentar_de_novo": "Tentar de novo",
    "celular.motivo.codigo_expirado": "QR code expirado. Escaneie de novo o código do telão.",
    "celular.motivo.sessao_fechada": "A votação não está aberta.",
    "celular.motivo.sessao_inexistente": "Votação não encontrada. Escaneie o código do telão.",
    "celular.motivo.cedula_invalida": "Escaneie de novo o QR code do telão.",
    "celular.motivo.ja_votou": "Este celular já votou nesta sessão ✓",
    "celular.motivo.cedula_usada": "Escaneie o QR code do telão para responder a próxima pergunta.",

    "mesario.titulo": "Veredito · Mesário",
    "mesario.sessao_ativa": "Sessão ativa",
    "mesario.nenhuma": "nenhuma",
    "mesario.votos": "Votos",
    "mesario.urnas": "Urnas",
    "mesario.recuperar": "Recuperar votos de urna isolada (arquivo exportado):",
    "mesario.sessoes": "Sessões",
    "mesario.mostrar_arquivadas": "mostrar arquivadas",
    "mesario.configuracao": "Configuração",
    "mesario.telao": "Telão",
    "mesario.telao_ajuda": "Abra o telão por este botão para exibir o QR code do voto por celular.",
    "mesario.abrir_telao": "Abrir telão com QR do celular",
    "mesario.monitoramento": "Monitoramento",
    "mesario.abrir_monitor": "Abrir painel de monitoramento",
    "mesario.monitor_ajuda": ": votos por minuto, latência e urnas online.",
    "mesario.criar_sessao": "Criar sessão",
    "mesario.mais_pergunta": "+ pergunta",
    "mesario.cadastrar_urna": "Cadastrar urna",
    "mesario.id_urna": "id (ex: urna3)",
    "mesario.nome_urna": "nome (ex: Entrada)",
    "mesario.reserva": "reserva",
    "mesario.cadastrar": "Cadastrar",
    "mesario.erro": "Erro {status}",
    "mesario.abrir_votacao": "Abrir votação",
    "mesario.encerrar_votacao": "Encerrar votação",
    "mesario.revelar_resultado": "Revelar resultado",
    "mesario.pergunta_prefixo": "Pergunta {n} de {total} · ",
    "mesario.liberar_pergunta": "Liberar pergunta {n}",
    "mesario.confirmar_liberar": "Liberar a pergunta {n} de {total}?",
    "mesario.arquivada": "arquivada",
    "mesario.desarquivar": "Desarquivar",
    "mesario.aguarda_anterior": "aguarda a revelação da pergunta anterior",
    "mesario.ativar": "Ativar",
    "mesario.arquivar": "Arquivar",
    "mesario.confirmar_arquivar": "Arquivar \"{tema}\"? Ela some da lista, mas pode ser desarquivada.",
    "mesario.zerar": "Zerar",
    "mesario.criar_preset": "Criar: {tema}",
    "mesario.rotulo": "rótulo",
    "mesario.remover": "remover",
    "mesario.tema_pergunta": "tema ou pergunta",
    "mesario.mais_opcao": "+ opção",
    "mesario.remover_pergunta": "remover pergunta",
    "mesario.legenda_pergunta": "Pergunta {n}",
    "mesario.opcao_padrao_1": "Acusação",
    "mesario.opcao_padrao_2": "Defesa",
    "mesario.preencha_opcoes": "Preencha todas as opções de \"{tema}\"",
    "mesario.opcoes_repetidas": "Há opções repetidas em \"{tema}\"",
    "mesario.confirmar_zerar": "Zerar apaga TODOS os votos de \"{tema}\" e volta a sessão para AGUARDANDO.\n\nPara confirmar, digite o tema da sessão:",
    "mesario.votos_apagados": "{n} votos apagados.",
    "mesario.confirmar_acao": "{acao}?",
    "mesario.pendencias": "Há pendências:\n\n{problemas}\n\nRevelar mesmo assim?",
    "mesario.reserva_marca": " (reserva)",
    "mesario.n_votos": "{n} votos",
    "mesario.desativada": "desativada",
    "mesario.nunca_conectou": "nunca conectou",
    "mesario.n_pendentes": "{n} pendentes",
    "mesario.offline_ha": "offline há {s}s",
    "mesario.n_recusados": "{n} votos recusados",
    "mesario.acoes": "Ações",
    "mesario.gerar_link": "Gerar novo link",
    "mesario.confirmar_link": "Gerar novo link para {id}? O link atual deixa de funcionar e a urna precisa ser reconfigurada.",
    "mesario.desativar": "Desativar",
    "mesario.confirmar_desativar": "Desativar {id}? Ela não poderá mais enviar votos.",
    "mesario.motivo.sessao_encerrada": "feitos depois do encerramento ou com a sessão já revelada",
    "mesario.motivo.sessao_nao_aberta": "sessão ainda não aberta",
    "mesario.motivo.sessao_inexistente": "sessão inexistente",
    "mesario.motivo.opcao_invalida": "opção inválida",
    "mesario.arquivo_invalido": "{arquivo}: não é um arquivo JSON válido.",
    "mesario.nao_e_fila": "{arquivo}: não é uma fila exportada pela urna.",
    "mesario.confirmar_importar": "Importar {n} votos da urna {urna}?",
    "mesario.importacao_origem": "Urna {urna} · arquivo de {quando}",
    "mesario.importacao_aceitos": "{n} votos aceitos",
    "mesario.importacao_existentes": "{n} já estavam no servidor (não duplicados)",
    "mesario.importacao_recusados": "{n} recusados",
    "mesario.importacao_motivo": "  · {n} {motivo}",
    "mesario.formato_invalido": "o arquivo tem votos em formato inválido",
    "mesario.falha_importar": "Falha ao importar: {erro}.",
    "mesario.link_pronto": "Link da urna {id} pronto. Mostre só na hora de configurar a urna.",
    "mesario.mostrar_link": "Mostrar link e QR code",
    "mesario.descartar": "Descartar",
    "mesario.abra_na_urna": "Abra na urna {id}. Oculta sozinho em {s}s.",
    "mesario.ocultar": "Ocultar"
  },
  "en": {
    "comum.carregando": "Loading…",
    "comum.confirmar": "Confirm",
    "comum.corrigir": "Change",
    "comum.confirmar_voto": "Confirm vote for {opcao}?",
    "comum.enviando": "Sending vote…",
    "comum.voto_registrado": "Vote recorded",
    "comum.pergunta_de": "Question {n} of {total}",
    "comum.senha": "Password",
    "comum.entrar": "Sign in",
    "comum.senha_incorreta": "Wrong password",
    "comum.trocar_idioma": "Switch to Portuguese",

    "estado.AGUARDANDO": "WAITING",
    "estado.ABERTA": "OPEN",
    "estado.ENCERRADA": "CLOSED",
    "estado.REVELADA": "REVEALED",

    "urna.titulo": "Veredicto · Ballot box",
    "urna.nao_configurada": "Ballot box not set up",
    "urna.fechada": "Voting closed",
    "urna.aguarde_proxima": "Wait for the next question",
    "urna.sem_conexao": "No connection: vote saved, it will be sent when the network is back",
    "urna.recusa.sessao_encerrada": "Vote NOT counted: voting has already closed",
    "urna.recusa.sessao_nao_aberta": "Vote NOT counted: voting has not opened yet",
    "urna.recusa.outra": "Vote NOT counted: the server rejected the vote",
    "urna.chame_mesario": "{motivo}. Call a poll worker.",
    "urna.entendi": "Got it",
    "urna.nao_autorizada": "ballot box not authorized",
    "urna.online": "online",
    "urna.offline": "offline",
    "urna.exportar": "export queue ({n})",

    "telao.titulo": "Veredito · Display",
    "telao.aguardando": "Waiting",
    "telao.legenda.AGUARDANDO": "voting not open yet",
    "telao.legenda.ABERTA": "votes recorded",
    "telao.legenda.ENCERRADA": "voting closed · waiting for the reveal",
    "telao.vote_celular": "Vote on your phone",

    "celular.titulo": "Veredicto · Vote on your phone",
    "celular.escaneie": "Scan the QR code shown on the display.",
    "celular.nao_entrou": "Could not join the vote.",
    "celular.encerrada": "Vote NOT counted: voting has already closed.",
    "celular.nao_computado": "Vote NOT counted. Please try again.",
    "celular.sem_conexao": "No connection to the server.",
    "celular.tentar_de_novo": "Try again",
    "celular.motivo.codigo_expirado": "QR code expired. Scan the code on the display again.",
    "celular.motivo.sessao_fechada": "Voting is not open.",
    "celular.motivo.sessao_inexistente": "Voting not found. Scan the code on the display.",
    "celular.motivo.cedula_invalida": "Scan the QR code on the display again.",
    "celular.motivo.ja_votou": "This phone has already voted in this session ✓",
    "celular.motivo.cedula_usada": "Scan the QR code on the display to answer the next question.",

    "mesario.titulo": "Veredito · Poll worker",
    "mesario.sessao_ativa": "Active session",
    "mesario.nenhuma": "none",
    "mesario.votos": "Votes",
    "mesario.urnas": "Ballot boxes",
    "mesario.recuperar": "Recover votes from an offline ballot box (exported file):",
    "mesario.sessoes": "Sessions",
    "mesario.mostrar_arquivadas": "show archived",
    "mesario.configuracao": "Settings",
    "mesario.telao": "Display",
    "mesario.telao_ajuda": "Open the display with this button to show the QR code for phone voting.",
    "mesario.abrir_telao": "Open display with phone QR code",
    "mesario.monitoramento": "Monitoring",
    "mesario.abrir_monitor": "Open monitoring dashboard",
    "mesario.monitor_ajuda": ": votes per minute, latency and ballot boxes online.",
    "mesario.criar_sessao": "Create session",
    "mesario.mais_pergunta": "+ question",
    "mesario.cadastrar_urna": "Register ballot box",
    "mesario.id_urna": "id (e.g. box3)",
    "mesario.nome_urna": "name (e.g. Entrance)",
    "mesario.reserva": "backup",
    "mesario.cadastrar": "Register",
    "mesario.erro": "Error {status}",
    "mesario.abrir_votacao": "Open voting",
    "mesario.encerrar_votacao": "Close voting",
    "mesario.revelar_resultado": "Reveal result",
    "mesario.pergunta_prefixo": "Question {n} of {total} · ",
    "mesario.liberar_pergunta": "Release question {n}",
    "mesario.confirmar_liberar": "Release question {n} of {total}?",
    "mesario.arquivada": "archived",
    "mesario.desarquivar": "Unarchive",
    "mesario.aguarda_anterior": "waiting for the previous question to be revealed",
    "mesario.ativar": "Activate",
    "mesario.arquivar": "Archive",
    "mesario.confirmar_arquivar": "Archive \"{tema}\"? It leaves the list but can be unarchived.",
    "mesario.zerar": "Reset",
    "mesario.criar_preset": "Create: {tema}",
    "mesario.rotulo": "label",
    "mesario.remover": "remove",
    "mesario.tema_pergunta": "topic or question",
    "mesario.mais_opcao": "+ option",
    "mesario.remover_pergunta": "remove question",
    "mesario.legenda_pergunta": "Question {n}",
    "mesario.opcao_padrao_1": "Prosecution",
    "mesario.opcao_padrao_2": "Defense",
    "mesario.preencha_opcoes": "Fill in every option of \"{tema}\"",
    "mesario.opcoes_repetidas": "There are repeated options in \"{tema}\"",
    "mesario.confirmar_zerar": "Reset deletes ALL votes of \"{tema}\" and sets the session back to WAITING.\n\nTo confirm, type the session topic:",
    "mesario.votos_apagados": "{n} votes deleted.",
    "mesario.confirmar_acao": "{acao}?",
    "mesario.pendencias": "There are pending issues:\n\n{problemas}\n\nReveal anyway?",
    "mesario.reserva_marca": " (backup)",
    "mesario.n_votos": "{n} votes",
    "mesario.desativada": "deactivated",
    "mesario.nunca_conectou": "never connected",
    "mesario.n_pendentes": "{n} pending",
    "mesario.offline_ha": "offline for {s}s",
    "mesario.n_recusados": "{n} votes rejected",
    "mesario.acoes": "Actions",
    "mesario.gerar_link": "Generate new link",
    "mesario.confirmar_link": "Generate a new link for {id}? The current link stops working and the ballot box must be set up again.",
    "mesario.desativar": "Deactivate",
    "mesario.confirmar_desativar": "Deactivate {id}? It will no longer be able to send votes.",
    "mesario.motivo.sessao_encerrada": "cast after closing or with the session already revealed",
    "mesario.motivo.sessao_nao_aberta": "session not open yet",
    "mesario.motivo.sessao_inexistente": "session not found",
    "mesario.motivo.opcao_invalida": "invalid option",
    "mesario.arquivo_invalido": "{arquivo}: not a valid JSON file.",
    "mesario.nao_e_fila": "{arquivo}: not a queue exported by a ballot box.",
    "mesario.confirmar_importar": "Import {n} votes from ballot box {urna}?",
    "mesario.importacao_origem": "Ballot box {urna} · file from {quando}",
    "mesario.importacao_aceitos": "{n} votes accepted",
    "mesario.importacao_existentes": "{n} were already on the server (not duplicated)",
    "mesario.importacao_recusados": "{n} rejected",
    "mesario.importacao_motivo": "  · {n} {motivo}",
    "mesario.formato_invalido": "the file has votes in an invalid format",
    "mesario.falha_importar": "Import failed: {erro}.",
    "mesario.link_pronto": "Link for ballot box {id} ready. Show it only when setting up the ballot box.",
    "mesario.mostrar_link": "Show link and QR code",
    "mesario.descartar": "Discard",
    "mesario.abra_na_urna": "Open on ballot box {id}. Hides itself in {s}s.",
    "mesario.ocultar": "Hide"
  }
} /* textos:fim */;

const IDIOMAS = ["pt", "en"];

const IDIOMA = (() => {
  try {
    const escolhido = localStorage.getItem("idioma");
    if (IDIOMAS.includes(escolhido)) return escolhido;
  } catch {
    // sem localStorage: segue o navegador
  }
  return (navigator.language || "").toLowerCase().startsWith("en") ? "en" : "pt";
})();

function t(chave, vars = {}) {
  const texto = TEXTOS[IDIOMA][chave] ?? TEXTOS.pt[chave] ?? chave;
  return texto.replace(/\{(\w+)\}/g, (_, nome) => vars[nome] ?? `{${nome}}`);
}

function traduzirPagina(raiz = document) {
  raiz.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  raiz.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
}

// mensagens do servidor no mesmo idioma da tela
const fetchOriginal = window.fetch.bind(window);
window.fetch = (recurso, opcoes = {}) => {
  const cabecalhos = new Headers(opcoes.headers ?? (recurso instanceof Request ? recurso.headers : undefined));
  if (!cabecalhos.has("Accept-Language")) cabecalhos.set("Accept-Language", IDIOMA);
  return fetchOriginal(recurso, { ...opcoes, headers: cabecalhos });
};

function seletorIdioma() {
  const outro = IDIOMA === "pt" ? "en" : "pt";
  const b = document.createElement("button");
  b.type = "button";
  b.id = "idioma";
  b.textContent = outro.toUpperCase();
  b.title = t("comum.trocar_idioma");
  b.setAttribute("aria-label", t("comum.trocar_idioma"));
  b.onclick = () => {
    try {
      localStorage.setItem("idioma", outro);
    } catch {
      return;
    }
    location.reload();
  };
  const estilo = document.createElement("style");
  estilo.textContent = `#idioma { position: fixed; top: 0.5rem; right: 0.5rem; z-index: 10; padding: 0.25rem 0.5rem;
    font: 600 0.8rem system-ui, sans-serif; border-radius: 0.375rem; border: 1px solid currentColor;
    background: transparent; color: inherit; opacity: 0.6; cursor: pointer; }
    #idioma:hover, #idioma:focus-visible { opacity: 1; }`;
  document.head.appendChild(estilo);
  document.body.appendChild(b);
}

document.documentElement.lang = IDIOMA === "en" ? "en" : "pt-BR";
traduzirPagina();
seletorIdioma();
