import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Leer la URL de la base de datos de Supabase desde variable de entorno
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:Tiablanca-1221@db.xgwiuldzahyudhouoene.supabase.co:5432/postgres"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")  # token simple para panel interno

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


class CreateLicenseRequest(BaseModel):
    """
    Modelo para crear licencias desde tu panel interno.
    - days_valid: número de días de validez (None = sin caducidad)
    """

    max_devices: int = 1
    days_valid: int | None = 365


class CreateLicenseResponse(BaseModel):
    license_key: str
    expires_at: datetime | None
    max_devices: int


@app.post("/admin/create_license", response_model=CreateLicenseResponse)
async def create_license(
    body: CreateLicenseRequest,
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
):
    """
    Endpoint interno para crear licencias nuevas.
    Protegido con un token simple en cabecera X-Admin-Token.
    """
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_TOKEN no está configurado en el servidor",
        )

    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    expires_at: datetime | None = None
    if body.days_valid is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.days_valid)

    license_id = uuid.uuid4()
    license_key = uuid.uuid4().hex[:16].upper()

    conn = await get_conn()
    try:
        await conn.execute(
            """
            INSERT INTO licenses (id, license_key, status, max_devices, expires_at)
            VALUES ($1, $2, 'active', $3, $4)
            """,
            license_id,
            license_key,
            body.max_devices,
            expires_at,
        )
    finally:
        await conn.close()

    return CreateLicenseResponse(
        license_key=license_key,
        expires_at=expires_at,
        max_devices=body.max_devices,
    )