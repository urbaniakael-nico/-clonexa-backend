"""Contenido de Nexa (plan B): laminas de carrusel con la plantilla de marca de Clonexa.

- POST /carousel: lo llama n8n ("Nexa - Plan B") con la cabecera X-Nexa-Token, el mismo token de
  servicio de /social-metrics/ingest (NEXA_INGEST_TOKEN, comparado en tiempo constante, 60 por
  minuto por IP; sin la variable 503, token mal 401). No es una funcion de ninguna empresa: es el
  marketing de la propia Clonexa, sin company_id, y no guarda nada (ni Postgres ni disco): dibuja con
  Pillow y devuelve los PNG en base64 para que n8n los suba a Drive.
"""
from __future__ import annotations

import base64
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.social_metrics import require_nexa_token
from app.services import nexa_carousel

router = APIRouter()


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return _clean(value) if isinstance(value, str) else value


class Cover(_Base):
    categoria: str = Field(default="", max_length=40)
    titulo: str = Field(min_length=1, max_length=90)
    resaltado: str = Field(default="", max_length=60)
    subtitulo: str = Field(default="", max_length=170)


class Point(_Base):
    titulo: str = Field(min_length=1, max_length=90)
    hoy: str = Field(min_length=1, max_length=220)
    con_clonexa: str = Field(min_length=1, max_length=220)


class Closing(_Base):
    titulo: str = Field(min_length=1, max_length=70)
    resaltado: str = Field(default="", max_length=50)
    texto: str = Field(default="", max_length=180)


class CarouselIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    portada: Cover
    puntos: list[Point] = Field(min_length=4, max_length=5)
    cierre: Closing
    nombre: Optional[str] = Field(default=None, max_length=120)


@router.post("/carousel", dependencies=[Depends(require_nexa_token)])
async def carousel(body: CarouselIn) -> dict:
    spec = body.model_dump()
    slides = await run_in_threadpool(nexa_carousel.render, spec)
    return {
        "count": len(slides),
        "width": nexa_carousel.W,
        "height": nexa_carousel.H,
        "slides": [
            {"name": f"{i:02d}.png", "mime": "image/png", "png_b64": base64.b64encode(png).decode("ascii")}
            for i, (png, _layout) in enumerate(slides, 1)
        ],
    }
