"""Configuracion de despliegue. La caida del 2026-11-03 (deploy 1beeeae9) fue una migracion que
fallo dentro del arranque, cuando Railway ya habia apagado el contenedor anterior: las migraciones
van en pre-deploy, y el arranque no migra."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _deploy() -> dict:
    return json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))["deploy"]


def test_las_migraciones_corren_en_pre_deploy():
    assert _deploy()["preDeployCommand"] == ["alembic upgrade head"]


def test_el_arranque_no_migra():
    lines = (ROOT / "scripts" / "start.sh").read_text(encoding="utf-8").splitlines()
    commands = [line for line in lines if not line.strip().startswith("#")]
    assert not [line for line in commands if "alembic" in line.lower()]
    assert any(line.startswith("exec uvicorn app.main:app") for line in commands)


def test_healthcheck_en_una_ruta_que_existe():
    deploy = _deploy()
    assert deploy["healthcheckPath"] == "/health" and deploy["healthcheckTimeout"] > 0
    assert '@app.get("/health")' in (ROOT / "app" / "main.py").read_text(encoding="utf-8")


def test_pre_deploy_encuentra_alembic_en_la_imagen():
    assert (ROOT / "alembic.ini").is_file()
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert not {"alembic.ini", "migrations", "migrations/"} & {line.strip() for line in ignored}
