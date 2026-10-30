"""Contrato de la API: qué entra y qué sale, con tipos y rangos validados por Pydantic.

Un request que no cumple el contrato se rechaza con 422 antes de tocar el modelo.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Indicadores(BaseModel):
    """Los 5 indicadores que usan el índice y el modelo de grupos."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pct_intervenidas": 0.95,
                "hhi": 7100,
                "ips_x_10mil": 0.8,
                "pct_rural": 0.8,
                "pct_subsidiado": 0.97,
            }
        }
    )

    pct_intervenidas: float = Field(
        ge=0, le=1, description="Proporción de afiliados en EPS intervenidas (0 a 1)"
    )
    hhi: float = Field(
        ge=0, le=10_000, description="Concentración de EPS, índice Herfindahl-Hirschman (0 a 10.000)"
    )
    ips_x_10mil: float = Field(ge=0, description="Sedes de IPS por cada 10.000 afiliados")
    pct_rural: float = Field(ge=0, le=1, description="Proporción de afiliados en zona rural (0 a 1)")
    pct_subsidiado: float = Field(
        ge=0, le=1, description="Proporción de afiliados en el régimen subsidiado (0 a 1)"
    )


class LoteIndicadores(BaseModel):
    municipios: list[Indicadores] = Field(min_length=1, max_length=2000)


class Componentes(BaseModel):
    dependencia: float
    oferta: float
    concentracion: float
    ruralidad: float
    subsidiado: float


class Prediccion(BaseModel):
    indice_riesgo: float = Field(description="0 = menor riesgo, 100 = mayor riesgo")
    nivel_riesgo: str = Field(description="Bajo, Medio, Alto o Muy alto")
    componentes: Componentes = Field(description="Percentil de cada componente (100 = más riesgo)")
    grupo: int = Field(description="Grupo del clustering; 1 = mayor riesgo promedio")
    nombre_grupo: str
    descripcion_grupo: str


class Metadata(BaseModel):
    request_id: str
    corte: str = Field(description="Fecha del corte de datos que sirve de referencia")
    modelo: str = Field(description="De dónde se cargó el modelo de grupos")
    latencia_ms: float


class RespuestaPrediccion(BaseModel):
    entrada: Indicadores
    prediccion: Prediccion
    metadata: Metadata


class RespuestaLote(BaseModel):
    predicciones: list[Prediccion]
    metadata: Metadata


class Municipio(BaseModel):
    cod_mpio: str
    nom_mpio: str
    dpto: str
    afiliados: float
    eps_principal: str | None
    sedes_ips: int
    pct_intervenidas: float
    hhi: float
    ips_x_10mil: float
    pct_rural: float
    pct_subsidiado: float
    indice_riesgo: float
    nivel_riesgo: str
    ranking_riesgo: int
    prob_top10: float = Field(
        description="Proporción de simulaciones de pesos en que quedó en el 10 % de mayor riesgo"
    )
    grupo: int
    nombre_grupo: str
    descripcion_grupo: str


class RespuestaMunicipios(BaseModel):
    total: int
    municipios: list[Municipio]
    metadata: Metadata


class Salud(BaseModel):
    estado: str
    corte: str
    municipios: int
    modelo: str
