"""Pydantic schemas for the Clima feature."""

from __future__ import annotations

from pydantic import BaseModel


class LeituraOni(BaseModel):
    trimestre: str
    ano: int
    anomalia: float


class LeituraSemanal(BaseModel):
    semana: str
    nino12: float
    nino3: float
    nino34: float
    nino4: float


class StatusEnso(BaseModel):
    alerta: str = ""
    sinopse: str = ""
    oni: list[LeituraOni] = []
    roni: list[LeituraOni] = []
    semanal: list[LeituraSemanal] = []

    @property
    def fase(self) -> str:
        """Classify the latest ONI value (NOAA thresholds)."""
        if not self.oni:
            return "indeterminada"
        v = self.oni[-1].anomalia
        if v >= 0.5:
            forca = (
                "muito forte"
                if v >= 2.0
                else "forte"
                if v >= 1.5
                else "moderado"
                if v >= 1.0
                else "fraco"
            )
            return f"El Niño {forca}"
        if v <= -0.5:
            forca = "forte" if v <= -1.5 else "moderada" if v <= -1.0 else "fraca"
            return f"La Niña {forca}"
        return "Neutra"


class AvisoInmet(BaseModel):
    evento: str = ""
    severidade: str = ""
    inicio: str = ""
    fim: str = ""
    descricao: str = ""
    area: str = ""
    link: str = ""


class Terremoto(BaseModel):
    magnitude: float
    local: str
    quando_ms: int
    link: str = ""
    tsunami: bool = False
    profundidade_km: float | None = None


class EventoNatural(BaseModel):
    titulo: str
    categoria: str
    data: str = ""
    link: str = ""


class LeituraEstacao(BaseModel):
    rotulo: str
    codigo: str
    nome: str
    distancia_km: float
    quando: str
    temperatura: float
    umidade: float | None = None
    vento_kmh: float | None = None
    rajada_kmh: float | None = None
    hoje_max: float | None = None
    hoje_min: float | None = None
    lat: float | None = None
    lon: float | None = None
