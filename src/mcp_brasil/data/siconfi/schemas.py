"""Pydantic schemas for the SICONFI API."""

from __future__ import annotations

from pydantic import BaseModel


class Ente(BaseModel):
    """Ente da federação cadastrado no SICONFI."""

    cod_ibge: int
    ente: str
    uf: str | None = None
    esfera: str | None = None
    regiao: str | None = None
    capital: str | None = None
    populacao: int | None = None
    cnpj: str | None = None


class LinhaDemonstrativo(BaseModel):
    """Uma célula (conta x coluna) de um demonstrativo fiscal."""

    exercicio: int | None = None
    periodo: int | None = None
    instituicao: str | None = None
    uf: str | None = None
    anexo: str | None = None
    coluna: str | None = None
    cod_conta: str | None = None
    conta: str | None = None
    valor: float | None = None


class Entrega(BaseModel):
    """Entrega de relatório/declaração ao SICONFI."""

    exercicio: int | None = None
    instituicao: str | None = None
    entregavel: str | None = None
    periodo: int | None = None
    periodicidade: str | None = None
    status_relatorio: str | None = None
    data_status: str | None = None
    forma_envio: str | None = None
