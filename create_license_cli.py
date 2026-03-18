import os

import requests
from dotenv import load_dotenv


def main():
    """
    Pequeño programa interno para crear licencias nuevas
    llamando al servidor de licencias en la nube.
    """
    load_dotenv()

    base_url = os.getenv(
        "LICENSE_SERVER_URL",
        "https://selectlive-licencias.onrender.com",
    ).rstrip("/")
    admin_token = os.getenv("ADMIN_TOKEN")

    if not admin_token:
        admin_token = input("Introduce ADMIN_TOKEN (solo para uso interno): ").strip()

    print("\n=== Crear nueva licencia SelectLive ===")

    try:
        max_devices = int(input("Número máximo de equipos (por defecto 1): ") or "1")
    except ValueError:
        max_devices = 1

    days_raw = input(
        "Días de validez (por defecto 365, vacío = sin caducidad): "
    ).strip()

    if not days_raw:
        days_valid = None
    else:
        try:
            days_valid = int(days_raw)
        except ValueError:
            days_valid = 365

    payload = {
        "max_devices": max_devices,
        "days_valid": days_valid,
    }

    try:
        resp = requests.post(
            f"{base_url}/admin/create_license",
            json=payload,
            headers={"X-Admin-Token": admin_token},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"\n[ERROR] No se pudo crear la licencia: {e}")
        return

    data = resp.json()
    print("\n=== LICENCIA CREADA ===")
    print(f"Clave de licencia: {data.get('license_key')}")
    print(f"Máx. equipos   : {data.get('max_devices')}")

    expires_at = data.get("expires_at")
    if expires_at:
        print(f"Caduca el      : {expires_at}")
    else:
        print("Caducidad      : Sin caducidad")

    print("\nEntrega esta clave al cliente para que la active en su programa.")


if __name__ == "__main__":
    main()

