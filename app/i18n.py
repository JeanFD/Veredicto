"""Mensagens que o servidor devolve às telas, em português e inglês.

O idioma vem do cabeçalho Accept-Language de cada requisição (as telas mandam o
idioma escolhido); sem ele, ou com outro idioma, vale o português. O campo
"motivo" das recusas não muda com o idioma: é ele que as telas e as métricas usam.
"""
from contextvars import ContextVar

IDIOMAS = ("pt", "en")

MENSAGENS = {
    # recusas de voto (o motivo é a própria chave)
    "sessao_inexistente": {"pt": "Sessão inexistente", "en": "Session not found"},
    "sessao_encerrada": {"pt": "Sessão encerrada", "en": "Session closed"},
    "sessao_nao_aberta": {"pt": "Sessão ainda não foi aberta", "en": "Session not open yet"},
    "opcao_invalida": {"pt": "Opção inválida", "en": "Invalid option"},
    "sessao_fechada": {"pt": "A votação não está aberta", "en": "Voting is not open"},
    "codigo_expirado": {
        "pt": "QR code expirado: escaneie de novo o código do telão",
        "en": "QR code expired: scan the code on the display again",
    },
    "cedula_invalida": {
        "pt": "Cédula inválida: escaneie o QR code do telão",
        "en": "Invalid ballot: scan the QR code on the display",
    },
    "sem_proxima": {
        "pt": "Não há outra pergunta deste questionário liberada",
        "en": "No other question of this questionnaire has been released",
    },
    "cedula_usada": {
        "pt": "Escaneie o QR code do telão para a próxima pergunta",
        "en": "Scan the QR code on the display for the next question",
    },
    "ja_votou": {"pt": "Este celular já votou nesta sessão", "en": "This phone has already voted in this session"},
    "voto_repetido": {"pt": "Voto repetido", "en": "Duplicate vote"},
    "celular_desligado": {
        "pt": "O voto por celular está desligado nesta sessão",
        "en": "Phone voting is turned off for this session",
    },
    "urna_de_teste": {
        "pt": "Urna de teste não vota em sessão de verdade",
        "en": "A test ballot box cannot vote in a real session",
    },

    # painel do mesário
    "ative_outra_antes": {"pt": "Ative outra sessão antes de arquivar esta", "en": "Activate another session before archiving this one"},
    "ja_revelada_zerar": {
        "pt": "Sessão já revelada: o resultado não pode ser apagado",
        "en": "Session already revealed: the result cannot be erased",
    },
    "confirmacao_nao_confere": {
        "pt": "Confirmação não confere com o tema da sessão",
        "en": "Confirmation does not match the session topic",
    },
    "opcoes_repetidas": {"pt": "Opções repetidas", "en": "Duplicate options"},
    "perguntas_repetidas": {"pt": "Perguntas repetidas", "en": "Duplicate questions"},
    "tema_existente": {"pt": "Já existe uma sessão com este tema", "en": "A session with this topic already exists"},
    "desarquive_antes": {"pt": "Desarquive a sessão antes de ativá-la", "en": "Unarchive the session before activating it"},
    "revele_anterior": {
        "pt": "Revele a pergunta anterior antes de liberar esta",
        "en": "Reveal the previous question before releasing this one",
    },
    "id_reservado": {"pt": "ID reservado para os votos por celular", "en": "ID reserved for phone votes"},
    "urna_existente": {"pt": "ID de urna já existe", "en": "Ballot box ID already exists"},
    "urna_inexistente": {"pt": "Urna inexistente", "en": "Ballot box not found"},
    "pedido_inexistente": {"pt": "Pedido de urna inexistente ou já atendido",
                           "en": "Ballot box request not found or already handled"},
    "pedido_expirado": {"pt": "Pedido recusado ou expirado", "en": "Request declined or expired"},
    "muitos_pedidos": {"pt": "Muitos pedidos de urna aguardando; tente em alguns minutos",
                       "en": "Too many ballot box requests waiting; try again in a few minutes"},
    "urna_desativada": {"pt": "Urna desativada", "en": "Ballot box deactivated"},
    "ative_antes": {"pt": "Ative a sessão antes", "en": "Activate the session first"},
    "ja_revelada": {"pt": "Sessão já revelada", "en": "Session already revealed"},
    "pendencias": {"pt": "Há pendências", "en": "There are pending issues"},
    "mudou_estado": {
        "pt": "A sessão mudou de estado nesse meio-tempo; atualize a tela",
        "en": "The session changed state in the meantime; refresh the page",
    },
    "exportacao_apos_revelar": {"pt": "Exportação liberada só após revelar", "en": "Export is available only after the reveal"},
    "auditoria_apos_revelar": {"pt": "Auditoria disponível só após a revelação", "en": "Audit is available only after the reveal"},

    # pendências antes de revelar
    "problema_nunca_conectou": {"pt": "{urna}: nunca conectou", "en": "{urna}: never connected"},
    "problema_offline": {
        "pt": "{urna}: offline há {s}s, pendências desconhecidas",
        "en": "{urna}: offline for {s}s, pending votes unknown",
    },
    "problema_pendentes": {"pt": "{urna}: {n} votos pendentes", "en": "{urna}: {n} pending votes"},

    # autenticação
    "muitas_tentativas": {"pt": "Muitas tentativas. Aguarde alguns minutos.", "en": "Too many attempts. Wait a few minutes."},
    "nao_autorizado": {"pt": "Não autorizado", "en": "Unauthorized"},
    "telao_nao_autorizado": {"pt": "Telão não autorizado", "en": "Display not authorized"},
    "urna_nao_autorizada": {"pt": "Urna não autorizada", "en": "Ballot box not authorized"},
}

idioma_atual: ContextVar[str] = ContextVar("idioma_atual", default="pt")


def idioma_do_cabecalho(accept_language: str | None) -> str:
    # só a primeira preferência importa: as telas mandam um idioma só
    primeiro = (accept_language or "").split(",")[0].strip().lower()
    return "en" if primeiro.startswith("en") else "pt"


def msg(chave: str, idioma: str | None = None, **campos) -> str:
    return MENSAGENS[chave][idioma or idioma_atual.get()].format(**campos)
