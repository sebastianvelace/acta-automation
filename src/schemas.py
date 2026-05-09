from __future__ import annotations

from pydantic import BaseModel, Field


class AsistenteSchema(BaseModel):
    nombre: str = Field(default="No especificado")
    puesto: str = Field(default="No especificado")


class AsuntoSchema(BaseModel):
    titulo: str
    descripcion: str


class CompromisoSchema(BaseModel):
    tarea: str
    responsable: str


class ActaSchema(BaseModel):
    titulo: str
    fecha: str
    hora_inicio: str
    hora_fin: str
    lugar: str
    cliente: str
    objetivo: str
    asistentes: list[AsistenteSchema]
    asuntos_tratados: list[AsuntoSchema]
    compromisos_gorila: list[CompromisoSchema]
    compromisos_cliente: list[CompromisoSchema]
