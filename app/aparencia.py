"""Aparência do telão: cores, textos e o jeito da revelação, mudados pelo admin no painel.

Fica numa linha só do banco, em JSON, e vai ao telão junto com o estado (e de novo
pelo WebSocket quando o admin salva). Texto vazio quer dizer o padrão da tradução,
no idioma da tela; texto escrito vale para os dois idiomas.
"""
import json

from pydantic import BaseModel, ConfigDict, Field

from app.db import db

COR = r"^#[0-9a-fA-F]{6}$"


class Cores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fundo: str = Field("#0b0c0a", pattern=COR)
    cartao: str = Field("#17191b", pattern=COR)
    destaque: str = Field("#d7f24e", pattern=COR)
    texto: str = Field("#f7f8f5", pattern=COR)


class Textos(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    aguardando: str = Field("", max_length=60)
    votos: str = Field("", max_length=60)
    vencedora: str = Field("", max_length=30)
    preferencia: str = Field("", max_length=40)
    celular: str = Field("", max_length=40)


class Revelacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regressiva: bool = True          # 3·2·1 antes dos cartões
    apuracao: bool = True            # números correndo de zero até o final
    duracao: float = Field(6.6, ge=2, le=20)  # segundos da apuração
    mostrar_votos: bool = True       # "12 votos" embaixo da porcentagem


class Aparencia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cores: Cores = Cores()
    textos: Textos = Textos()
    revelacao: Revelacao = Revelacao()


def ler() -> dict:
    linha = db.execute("SELECT config FROM aparencia_telao WHERE id = 1").fetchone()
    salvo = json.loads(linha["config"]) if linha else {}
    try:
        return Aparencia.model_validate(salvo).model_dump()
    except ValueError:
        # uma configuração que não vale mais (campo removido, limite novo) volta ao padrão
        return Aparencia().model_dump()


def gravar(aparencia: Aparencia) -> dict:
    with db:
        db.execute("UPDATE aparencia_telao SET config = ? WHERE id = 1",
                   (json.dumps(aparencia.model_dump(), ensure_ascii=False),))
    return ler()


def diferencas(antes: dict, depois: dict) -> list[str]:
    """Nomes dos campos que mudaram ("cores.destaque"), para o registro do painel."""
    return [f"{grupo}.{campo}" for grupo in depois for campo in depois[grupo]
            if antes.get(grupo, {}).get(campo) != depois[grupo][campo]]
