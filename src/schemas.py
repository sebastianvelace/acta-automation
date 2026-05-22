from __future__ import annotations

from pydantic import BaseModel, Field


class InvitadoSchema(BaseModel):
    correo: str = Field(default="")
    nombre: str = Field(default="")
    puesto: str = Field(default="")
    asistencia: str = Field(default="Confirmado")


class AsuntoSchema(BaseModel):
    titulo: str
    descripcion: str


class CompromisoSchema(BaseModel):
    tarea: str
    responsable: str
    fecha_entrega: str = Field(default="No especificada")


class ActaSchema(BaseModel):
    titulo: str
    fecha: str
    hora_inicio: str
    hora_fin: str
    lugar: str
    cliente: str
    objetivo: str
    cierre: str = Field(default="")
    invitados: list[InvitadoSchema]
    asuntos_tratados: list[AsuntoSchema]
    compromisos_gorila: list[CompromisoSchema]
    compromisos_cliente: list[CompromisoSchema]
