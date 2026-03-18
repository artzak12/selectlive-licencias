"""
Pequeña aplicación de escritorio para crear licencias de SelectLive.
Usa la misma paleta de colores que el launcher del programa.
"""

import os
import tkinter as tk
from tkinter import messagebox

import requests
from dotenv import load_dotenv


def cargar_config():
    """
    Carga LICENSE_SERVER_URL y ADMIN_TOKEN desde .env o variables de entorno.
    """
    load_dotenv()

    base_url = os.getenv(
        "LICENSE_SERVER_URL",
        "https://selectlive-licencias.onrender.com",
    ).rstrip("/")
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()

    return base_url, admin_token


class LicenseCreatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SelectLive - Creador de licencias")
        self.root.configure(bg="#101820")
        self.root.geometry("520x260")
        self.root.resizable(False, False)

        # Centrar ventana
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"520x260+{x}+{y}")

        self.base_url, self.admin_token = cargar_config()

        self._build_ui()

    def _build_ui(self):
        # Título
        title = tk.Label(
            self.root,
            text="Creador de licencias SelectLive",
            font=("Segoe UI", 16, "bold"),
            fg="#1E90FF",
            bg="#101820",
        )
        title.pack(pady=(15, 5))

        subtitle = tk.Label(
            self.root,
            text="Genera claves de licencia para tus clientes",
            font=("Segoe UI", 10),
            fg="#B0B0B0",
            bg="#101820",
        )
        subtitle.pack(pady=(0, 15))

        form_frame = tk.Frame(self.root, bg="#101820")
        form_frame.pack(pady=(0, 10))

        # Número máximo de equipos
        lbl_devices = tk.Label(
            form_frame,
            text="Número máximo de equipos:",
            font=("Segoe UI", 10),
            fg="#B0B0B0",
            bg="#101820",
            anchor="w",
        )
        lbl_devices.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.entry_devices = tk.Entry(
            form_frame,
            font=("Segoe UI", 10),
            width=10,
        )
        self.entry_devices.insert(0, "1")
        self.entry_devices.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Días de validez
        lbl_days = tk.Label(
            form_frame,
            text="Días de validez (vacío = sin caducidad):",
            font=("Segoe UI", 10),
            fg="#B0B0B0",
            bg="#101820",
            anchor="w",
        )
        lbl_days.grid(row=1, column=0, sticky="w", padx=5, pady=5)

        self.entry_days = tk.Entry(
            form_frame,
            font=("Segoe UI", 10),
            width=10,
        )
        self.entry_days.insert(0, "365")
        self.entry_days.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # Separador
        sep = tk.Frame(self.root, bg="#151F2B", height=1)
        sep.pack(fill="x", padx=20, pady=(5, 10))

        # Botón crear
        btn_crear = tk.Button(
            self.root,
            text="Crear licencia",
            font=("Segoe UI", 12, "bold"),
            width=18,
            bg="#1E90FF",
            fg="white",
            activebackground="#00A8FF",
            activeforeground="white",
            relief="flat",
            command=self.crear_licencia,
        )
        btn_crear.pack(pady=(0, 10))

        # Resultado
        self.result_text = tk.Text(
            self.root,
            height=4,
            width=60,
            font=("Segoe UI", 9),
            bg="#101820",
            fg="#B0B0B0",
            relief="flat",
        )
        self.result_text.pack(pady=(0, 5))
        self.result_text.insert(
            "1.0",
            "Aquí aparecerá la clave de licencia generada.",
        )
        self.result_text.config(state="disabled")

        footer = tk.Label(
            self.root,
            text="© 2026 SelectLive. Uso interno.",
            font=("Segoe UI", 8),
            fg="#555555",
            bg="#101820",
        )
        footer.pack(pady=(0, 8))

    def _set_result(self, text: str):
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.config(state="disabled")

    def crear_licencia(self):
        # Validar ADMIN_TOKEN
        if not self.admin_token:
            messagebox.showerror(
                "Error de configuración",
                "ADMIN_TOKEN no está configurado.\n"
                "Configúralo en el archivo .env o como variable de entorno.",
            )
            return

        # Leer número de equipos
        try:
            max_devices = int(self.entry_devices.get().strip() or "1")
        except ValueError:
            messagebox.showerror(
                "Dato no válido",
                "El número máximo de equipos debe ser un número entero.",
            )
            return

        # Leer días de validez
        days_raw = self.entry_days.get().strip()
        if not days_raw:
            days_valid = None
        else:
            try:
                days_valid = int(days_raw)
            except ValueError:
                messagebox.showerror(
                    "Dato no válido",
                    "Los días de validez deben ser un número entero o dejarse vacío.",
                )
                return

        payload = {
            "max_devices": max_devices,
            "days_valid": days_valid,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/admin/create_license",
                json=payload,
                headers={"X-Admin-Token": self.admin_token},
                timeout=10,
            )
        except Exception as e:
            messagebox.showerror(
                "Error de conexión",
                f"No se pudo contactar con el servidor de licencias:\n{e}",
            )
            return

        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            messagebox.showerror(
                "Error al crear licencia",
                f"Código {resp.status_code}:\n{detail}",
            )
            return

        data = resp.json()
        license_key = data.get("license_key")
        max_dev = data.get("max_devices")
        expires_at = data.get("expires_at")

        texto = f"Clave de licencia: {license_key}\nMáx. equipos: {max_dev}"
        if expires_at:
            texto += f"\nCaduca el: {expires_at}"
        else:
            texto += "\nCaducidad: Sin caducidad"

        self._set_result(texto)

        messagebox.showinfo(
            "Licencia creada",
            "Licencia creada correctamente.\n"
            "Copia la clave y entrégasela al cliente.",
        )


def main():
    root = tk.Tk()
    app = LicenseCreatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

