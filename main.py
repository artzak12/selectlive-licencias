import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncpg
from dotenv import load_dotenv

# Leer la URL de la base de datos de Supabase desde variable de entorno
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:Tiablanca-1221@db.xgwiuldzahyudhouoene.supabase.co:5432/postgres"

app = FastAPI(title="SelectLive License Server")


async def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está definida en el entorno")
    return await asyncpg.connect(DATABASE_URL)


class ActivateRequest(BaseModel):
    license_key: str
    machine_id: str


class ActivateResponse(BaseModel):
    activation_token: str


@app.post("/activate", response_model=ActivateResponse)
async def activate(req: ActivateRequest):
    conn = await get_conn()
    try:
        lic = await conn.fetchrow(
            "SELECT * FROM licenses WHERE license_key = $1",
            req.license_key.strip(),
        )
        if not lic:
            raise HTTPException(status_code=400, detail="Licencia no válida")

        if lic["status"] != "active":
            raise HTTPException(status_code=403, detail="Licencia no activa")

        if lic["expires_at"] and lic["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Licencia caducada")

        # Número de activaciones actuales
        activaciones = await conn.fetchval(
            "SELECT COUNT(*) FROM license_activations WHERE license_id = $1",
            lic["id"],
        )

        # ¿ya está activada en esta máquina?
        activacion_existente = await conn.fetchrow(
            """
            SELECT * FROM license_activations
            WHERE license_id = $1 AND machine_id = $2
            """,
            lic["id"],
            req.machine_id,
        )

        if not activacion_existente and activaciones >= lic["max_devices"]:
            raise HTTPException(status_code=403, detail="Demasiados dispositivos")

        # Insertar o actualizar activación
        await conn.execute(
            """
            INSERT INTO license_activations (id, license_id, machine_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (license_id, machine_id) DO UPDATE
            SET last_seen = now()
            """,
            uuid.uuid4(),
            lic["id"],
            req.machine_id,
        )

        # Token sencillo (luego podemos mejorarlo a JWT)
        token = f"{lic['license_key']}::{req.machine_id}"
        return ActivateResponse(activation_token=token)
    finally:
        await conn.close()


class CheckRequest(BaseModel):
    activation_token: str
    machine_id: str


@app.post("/check")
async def check(req: CheckRequest):
    # Extraer datos del token
    try:
        license_key, machine_id = req.activation_token.split("::", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Token no válido")

    if machine_id != req.machine_id:
        raise HTTPException(status_code=403, detail="Token no válido para este equipo")

    conn = await get_conn()
    try:
        lic = await conn.fetchrow(
            "SELECT * FROM licenses WHERE license_key = $1",
            license_key,
        )
        if not lic or lic["status"] != "active":
            raise HTTPException(status_code=403, detail="Licencia no activa")

        if lic["expires_at"] and lic["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Licencia caducada")

        # Actualizar last_seen
        await conn.execute(
            """
            UPDATE license_activations
            SET last_seen = now()
            WHERE license_id = $1 AND machine_id = $2
            """,
            lic["id"],
            machine_id,
        )
    finally:
        await conn.close()

    return {"ok": True}