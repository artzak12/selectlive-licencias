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


async def _archive_expired() -> None:
    """
    Archiva licencias caducadas (sin borrarlas):
    - pone licenses.status = 'expired'
    - marca issued_licenses.archived_at

    Así se mantienen en histórico y el panel puede mostrarlas como CADUCADO.
    """
    conn = await get_conn()
    try:
        async with conn.transaction():
            expired = await conn.fetch(
                """
                SELECT id
                FROM licenses
                WHERE expires_at IS NOT NULL
                  AND expires_at < now()
                """
            )
            if not expired:
                return

            expired_ids = [r["id"] for r in expired]

            await conn.execute(
                """
                UPDATE licenses
                SET status = 'expired'
                WHERE id = ANY($1::uuid[])
                """,
                expired_ids,
            )

            await conn.execute(
                """
                UPDATE issued_licenses
                SET archived_at = COALESCE(archived_at, now())
                WHERE license_id = ANY($1::uuid[])
                """,
                expired_ids,
            )
    finally:
        await conn.close()


async def _ensure_admin_tables() -> None:
    """
    Crea (si no existen) las tablas auxiliares para el panel interno.

    Nota: no tocamos el esquema principal de licencias para no romper /activate y /check.
    """
    conn = await get_conn()
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS issued_licenses (
              id uuid PRIMARY KEY,
              license_id uuid NOT NULL,
              license_key text NOT NULL UNIQUE,
              customer_name text NOT NULL DEFAULT '',
              customer_phone text NOT NULL DEFAULT '',
              duration_label text NOT NULL DEFAULT '',
              expires_at timestamptz NULL,
              created_at timestamptz NOT NULL DEFAULT now(),
              archived_at timestamptz NULL
            );
            """
        )
        # Si ya existía la tabla, asegura la columna
        await conn.execute(
            "ALTER TABLE issued_licenses ADD COLUMN IF NOT EXISTS archived_at timestamptz NULL"
        )
    finally:
        await conn.close()


@app.on_event("startup")
async def _startup():
    await _ensure_admin_tables()
    await _archive_expired()


class ActivateRequest(BaseModel):
    license_key: str
    machine_id: str


class ActivateResponse(BaseModel):
    activation_token: str


@app.post("/activate", response_model=ActivateResponse)
async def activate(req: ActivateRequest):
    await _archive_expired()
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
    await _archive_expired()
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

        expires_at = lic["expires_at"]
        now = datetime.now(timezone.utc)

        # Comprobar caducidad
        if expires_at and expires_at < now:
            raise HTTPException(status_code=403, detail="Licencia caducada")

        # Calcular días restantes (si hay fecha de caducidad)
        days_left: int | None = None
        if expires_at is not None:
            diff = expires_at - now
            days_left = max(diff.days, 0)

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

    return {
        "ok": True,
        "status": "active",
        "expires_at": expires_at.isoformat() if expires_at else None,
        "days_left": days_left,
    }


class CreateLicenseRequest(BaseModel):
    """
    Modelo para crear licencias desde tu panel interno.
    - days_valid: número de días de validez (None = sin caducidad)
    """

    max_devices: int = 1
    # Compatibilidad: los primeros scripts usaban days_valid directamente.
    days_valid: int | None = 365
    # Nuevos campos para panel interno
    customer_name: str = ""
    customer_phone: str = ""
    duration_label: str = ""  # p.ej: "3 días", "1 mes", "Permanente"


class CreateLicenseResponse(BaseModel):
    license_key: str
    expires_at: datetime | None
    max_devices: int
    customer_name: str | None = None
    customer_phone: str | None = None
    duration_label: str | None = None


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

    # Resolver duración
    duration_map = {
        "3 días": 3,
        "1 mes": 30,
        "3 meses": 90,
        "6 meses": 180,
        "12 meses": 365,
        "Permanente": None,
        "": body.days_valid,  # compatibilidad
    }

    resolved_days = duration_map.get(body.duration_label, body.days_valid)

    expires_at: datetime | None = None
    if resolved_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=int(resolved_days))

    license_id = uuid.uuid4()
    license_key = uuid.uuid4().hex[:16].upper()

    conn = await get_conn()
    try:
        async with conn.transaction():
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

            await conn.execute(
                """
                INSERT INTO issued_licenses (
                  id, license_id, license_key,
                  customer_name, customer_phone, duration_label, expires_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (license_key) DO NOTHING
                """,
                uuid.uuid4(),
                license_id,
                license_key,
                (body.customer_name or "").strip(),
                (body.customer_phone or "").strip(),
                (body.duration_label or "").strip(),
                expires_at,
            )
    finally:
        await conn.close()

    return CreateLicenseResponse(
        license_key=license_key,
        expires_at=expires_at,
        max_devices=body.max_devices,
        customer_name=(body.customer_name or "").strip() or None,
        customer_phone=(body.customer_phone or "").strip() or None,
        duration_label=(body.duration_label or "").strip() or None,
    )


class ExtendLicenseRequest(BaseModel):
    duration_label: str  # "3 días" / "1 mes" / ... / "Permanente"


@app.post("/admin/extend_license/{license_key}")
async def extend_license(
    license_key: str,
    body: ExtendLicenseRequest,
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_TOKEN no está configurado en el servidor",
        )

    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    await _archive_expired()

    duration_map = {
        "3 días": 3,
        "1 mes": 30,
        "3 meses": 90,
        "6 meses": 180,
        "12 meses": 365,
        "Permanente": None,
    }

    if body.duration_label not in duration_map:
        raise HTTPException(status_code=400, detail="Duración no válida")

    add_days = duration_map[body.duration_label]

    conn = await get_conn()
    try:
        lic = await conn.fetchrow(
            "SELECT id, expires_at FROM licenses WHERE license_key = $1",
            license_key.strip(),
        )
        if not lic:
            raise HTTPException(status_code=404, detail="Licencia no encontrada")

        # Base: si estaba caducada, sumamos desde "ahora"; si no, desde su expires_at
        now = datetime.now(timezone.utc)
        current_expires = lic["expires_at"]

        if add_days is None:
            new_expires = None
        else:
            base = current_expires if (current_expires and current_expires > now) else now
            new_expires = base + timedelta(days=int(add_days))

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE licenses
                SET expires_at = $2,
                    status = 'active'
                WHERE id = $1
                """,
                lic["id"],
                new_expires,
            )

            await conn.execute(
                """
                UPDATE issued_licenses
                SET expires_at = $2,
                    duration_label = $3,
                    archived_at = NULL
                WHERE license_key = $1
                """,
                license_key.strip(),
                new_expires,
                body.duration_label,
            )
    finally:
        await conn.close()

    return {"ok": True, "expires_at": new_expires}


class ClientRow(BaseModel):
    customer_name: str
    customer_phone: str
    duration_label: str
    license_key: str
    expires_at: datetime | None
    created_at: datetime
    archived_at: datetime | None
    is_expired: bool


@app.get("/admin/clients", response_model=list[ClientRow])
async def list_clients(
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_TOKEN no está configurado en el servidor",
        )

    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    await _archive_expired()

    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT customer_name, customer_phone, duration_label, license_key, expires_at, created_at, archived_at,
                   (expires_at IS NOT NULL AND expires_at < now()) AS is_expired
            FROM issued_licenses
            ORDER BY created_at DESC
            """
        )
        return [
            ClientRow(
                customer_name=r["customer_name"] or "",
                customer_phone=r["customer_phone"] or "",
                duration_label=r["duration_label"] or "",
                license_key=r["license_key"],
                expires_at=r["expires_at"],
                created_at=r["created_at"],
                archived_at=r["archived_at"],
                is_expired=bool(r["is_expired"]),
            )
            for r in rows
        ]
    finally:
        await conn.close()


@app.delete("/admin/license/{license_key}")
async def delete_license(
    license_key: str,
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_TOKEN no está configurado en el servidor",
        )

    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")

    conn = await get_conn()
    try:
        lic = await conn.fetchrow(
            "SELECT id FROM licenses WHERE license_key = $1",
            license_key.strip(),
        )
        if not lic:
            raise HTTPException(status_code=404, detail="Licencia no encontrada")

        license_id = lic["id"]
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM license_activations WHERE license_id = $1",
                license_id,
            )
            await conn.execute(
                "DELETE FROM issued_licenses WHERE license_id = $1",
                license_id,
            )
            await conn.execute(
                "DELETE FROM licenses WHERE id = $1",
                license_id,
            )
    finally:
        await conn.close()

    return {"ok": True}
