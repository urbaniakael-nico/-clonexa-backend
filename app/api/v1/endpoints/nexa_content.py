"""Contenido de Nexa (plan B): laminas de carrusel con la plantilla de marca de Clonexa.

- POST /carousel: lo llama n8n ("Nexa - Plan B") con la cabecera X-Nexa-Token, el mismo token de
  servicio de /social-metrics/ingest (NEXA_INGEST_TOKEN, comparado en tiempo constante, 60 por
  minuto por IP; sin la variable 503, token mal 401). No es una funcion de ninguna empresa: es el
  marketing de la propia Clonexa, sin company_id, y no guarda nada (ni Postgres ni disco): dibuja con
  Pillow y devuelve los PNG en base64 para que n8n los suba a Drive.
- POST /ad: mismo token. Anuncio visual de una imagen 1080x1350 (plan B desde el 11 nov): escena de
  un catalogo cerrado de pantallas de empresas DEMO (no acepta imagenes ni rutas), titular de maximo
  8 palabras, 4-5 funciones con emoji. Tampoco guarda nada.
- POST /jpeg: mismo token. Recibe los bytes de una imagen y devuelve JPEG (Instagram solo publica
  JPEG por URL); lo usa el enlace temporal de n8n ("Nexa - Archivo temporal"). Tampoco guarda nada.
"""
from __future__ import annotations

import base64
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.social_metrics import require_nexa_token
from app.services import nexa_ad, nexa_carousel

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


MAX_IMAGE = 15_000_000


@router.post("/jpeg", dependencies=[Depends(require_nexa_token)])
async def to_jpeg(request: Request) -> Response:
    """PNG (u otra imagen) -> JPEG calidad 92, mismo tamano. Instagram solo publica JPEG por URL."""
    raw = await request.body()
    if not raw or len(raw) > MAX_IMAGE:
        raise HTTPException(status_code=413 if raw else 400, detail="image_size")
    try:
        data = await run_in_threadpool(nexa_carousel.to_jpeg, raw)
    except Exception:
        raise HTTPException(status_code=400, detail="not_an_image")
    return Response(content=data, media_type="image/jpeg")


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


class Feature(_Base):
    emoji: str = Field(default="✅", max_length=16)
    texto: str = Field(min_length=1, max_length=28)


class AdIn(_Base):
    escena: str
    tag: str = Field(default="", max_length=28)
    titulo: str = Field(min_length=1, max_length=80)
    resaltado: str = Field(default="", max_length=60)
    remate: str = Field(default="", max_length=40)
    subtitulo: str = Field(default="", max_length=110)
    funciones: list[Feature] = Field(min_length=4, max_length=5)
    cta: str = Field(default="Pide tu demo gratis", max_length=30)

    @field_validator("escena")
    @classmethod
    def _scene(cls, value: str) -> str:
        if value not in nexa_ad.SCENES:
            raise ValueError("escena desconocida: " + ", ".join(nexa_ad.SCENES))
        return value

    @model_validator(mode="after")
    def _words(self) -> "AdIn":
        if nexa_ad.title_words(self.titulo, self.resaltado, self.remate) > nexa_ad.MAX_TITLE_WORDS:
            raise ValueError(f"el titular tiene mas de {nexa_ad.MAX_TITLE_WORDS} palabras")
        return self


@router.post("/ad", dependencies=[Depends(require_nexa_token)])
async def ad(body: AdIn) -> dict:
    png, _layout = await run_in_threadpool(nexa_ad.render, body.model_dump())
    return {"name": "anuncio.png", "mime": "image/png", "width": nexa_ad.W, "height": nexa_ad.H, "escena": body.escena,
            "png_b64": base64.b64encode(png).decode("ascii")}


@router.get("/ad/escenas", dependencies=[Depends(require_nexa_token)])
async def ad_scenes() -> dict:
    return {"escenas": {k: {"rubro": v["rubro"], "tag": v["tag"]} for k, v in nexa_ad.SCENES.items()},
            "emoji": list(nexa_ad.EMOJI), "max_palabras_titular": nexa_ad.MAX_TITLE_WORDS}
