"""
Pequeña aplicación de escritorio para crear licencias de SelectLive.
Usa la misma paleta de colores que el launcher del programa.
"""

import os
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import simpledialog
from datetime import datetime, timezone

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
        self.root.title("SelectLive - Panel de licencias")
        self.root.configure(bg="#101820")
        self.root.geometry("1100x600")
        self.root.resizable(True, True)

        # Centrar ventana
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"1100x600+{x}+{y}")

        self.base_url, self.admin_token = cargar_config()

        # Mantener referencia para que no lo recoja el GC
        self._logo_img = None
        self._clients_cache: list[tuple] = []

        self._build_ui()
        self._refresh_clients()

    def _build_ui(self):
        # Estilos ttk en oscuro
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TNotebook", background="#101820", borderwidth=0)
        style.configure("TNotebook.Tab", background="#151F2B", foreground="#B0B0B0", padding=[10, 6])
        style.map("TNotebook.Tab", background=[("selected", "#1E90FF")], foreground=[("selected", "white")])

        style.configure(
            "Treeview",
            background="#101820",
            fieldbackground="#101820",
            foreground="#B0B0B0",
            rowheight=24,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background="#151F2B",
            foreground="#B0B0B0",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview", background=[("selected", "#1E90FF")], foreground=[("selected", "white")])
        style.configure("Expired.Treeview", foreground="#E74C3C")

        # Logo superior (si existe)
        logo_frame = tk.Frame(self.root, bg="#101820")
        logo_frame.pack(pady=(15, 5))

        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "logo_licencias.png")

        if os.path.exists(logo_path):
            try:
                self._logo_img = tk.PhotoImage(file=logo_path)
            except Exception:
                self._logo_img = None

        if self._logo_img:
            tk.Label(logo_frame, image=self._logo_img, bg="#101820").pack()
        else:
            tk.Label(
                logo_frame,
                text="Panel interno de licencias",
                font=("Segoe UI", 16, "bold"),
                fg="#1E90FF",
                bg="#101820",
            ).pack()

        subtitle = tk.Label(
            self.root,
            text="Crea licencias y gestiona tus clientes",
            font=("Segoe UI", 10),
            fg="#B0B0B0",
            bg="#101820",
        )
        subtitle.pack(pady=(0, 15))

        # Tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        self.tab_clients = tk.Frame(notebook, bg="#101820")
        self.tab_create = tk.Frame(notebook, bg="#101820")

        notebook.add(self.tab_clients, text="Clientes")
        notebook.add(self.tab_create, text="Crear licencia")

        self._build_clients_tab()
        self._build_create_tab()

        footer = tk.Label(
            self.root,
            text="© 2026 SelectLive. Uso interno.",
            font=("Segoe UI", 8),
            fg="#555555",
            bg="#101820",
        )
        footer.pack(pady=(0, 10))

    def _build_clients_tab(self):
        top = tk.Frame(self.tab_clients, bg="#101820")
        top.pack(fill="x", pady=(5, 8))

        # Buscador
        tk.Label(
            top,
            text="Buscar:",
            font=("Segoe UI", 10),
            fg="#B0B0B0",
            bg="#101820",
        ).pack(side="left", padx=(5, 6))

        self.search_var = tk.StringVar(value="")
        self.entry_search = tk.Entry(
            top,
            textvariable=self.search_var,
            font=("Segoe UI", 10),
            width=35,
        )
        self.entry_search.pack(side="left", padx=(0, 10))
        self.entry_search.bind("<KeyRelease>", lambda _e: self._apply_filter())

        btn_copy_mail = tk.Button(
            top,
            text="✉ Copiar mail",
            font=("Segoe UI", 10, "bold"),
            bg="#1E90FF",
            fg="white",
            activebackground="#00A8FF",
            activeforeground="white",
            relief="flat",
            command=self._copy_mail_for_selected,
        )
        btn_copy_mail.pack(side="right", padx=5)

        btn_extend = tk.Button(
            top,
            text="➕ Añadir tiempo",
            font=("Segoe UI", 10, "bold"),
            bg="#58D68D",
            fg="white",
            activebackground="#2ECC71",
            activeforeground="white",
            relief="flat",
            command=self._extend_selected_license,
        )
        btn_extend.pack(side="right", padx=5)

        btn_copy = tk.Button(
            top,
            text="⧉ Copiar clave",
            font=("Segoe UI", 10, "bold"),
            bg="#1E90FF",
            fg="white",
            activebackground="#00A8FF",
            activeforeground="white",
            relief="flat",
            command=self._copy_selected_license,
        )
        btn_copy.pack(side="right", padx=5)

        btn_delete = tk.Button(
            top,
            text="🗑 Eliminar licencia",
            font=("Segoe UI", 10, "bold"),
            bg="#EC7063",
            fg="white",
            activebackground="#E74C3C",
            activeforeground="white",
            relief="flat",
            command=self._delete_selected_license,
        )
        btn_delete.pack(side="right", padx=5)

        btn_refresh = tk.Button(
            top,
            text="↻ Actualizar",
            font=("Segoe UI", 10, "bold"),
            bg="#1E90FF",
            fg="white",
            activebackground="#00A8FF",
            activeforeground="white",
            relief="flat",
            command=self._refresh_clients,
        )
        btn_refresh.pack(side="right", padx=5)

        cols = ("nombre", "telefono", "duracion", "caducidad", "restante", "licencia")
        self.tree = ttk.Treeview(self.tab_clients, columns=cols, show="headings", height=12)

        self.tree.heading("nombre", text="Nombre")
        self.tree.heading("telefono", text="Teléfono")
        self.tree.heading("duracion", text="Duración")
        self.tree.heading("caducidad", text="Caducidad")
        self.tree.heading("restante", text="Tiempo restante")
        self.tree.heading("licencia", text="Clave")

        self.tree.column("nombre", width=160, anchor="w")
        self.tree.column("telefono", width=110, anchor="w")
        self.tree.column("duracion", width=90, anchor="w")
        self.tree.column("caducidad", width=140, anchor="w")
        self.tree.column("restante", width=140, anchor="w")
        self.tree.column("licencia", width=150, anchor="w")

        self.tree.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        self.tree.tag_configure("expired", foreground="#E74C3C")
        self.tree.bind("<Double-1>", lambda _e: self._copy_selected_license())

    def _apply_filter(self):
        q = (self.search_var.get() or "").strip().lower()

        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not q:
            rows = self._clients_cache
        else:
            rows = []
            for values, tags in self._clients_cache:
                nombre, telefono, _duracion, _caducidad, _restante, clave = values
                hay = (
                    (str(nombre).lower().find(q) != -1)
                    or (str(telefono).lower().find(q) != -1)
                    or (str(clave).lower().find(q) != -1)
                )
                if hay:
                    rows.append((values, tags))

        for values, tags in rows:
            self.tree.insert("", "end", values=values, tags=tags)

    def _get_selected_row(self) -> tuple | None:
        sel = self.tree.selection()
        if not sel:
            return None
        values = self.tree.item(sel[0], "values")
        if not values or len(values) < 6:
            return None
        return values

    def _get_selected_license_key(self) -> str | None:
        values = self._get_selected_row()
        if not values:
            return None
        return str(values[5])

    def _copy_selected_license(self):
        license_key = self._get_selected_license_key()
        if not license_key:
            messagebox.showwarning(
                "Selecciona una fila",
                "Selecciona un cliente/licencia en la tabla para copiar la clave.",
            )
            return

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(license_key)
            self.root.update()  # asegura que se copie incluso si se cierra rápido
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo copiar al portapapeles:\n{e}")
            return

        messagebox.showinfo("Copiado", f"Clave copiada:\n\n{license_key}")

    def _copy_mail_for_selected(self):
        values = self._get_selected_row()
        if not values:
            messagebox.showwarning(
                "Selecciona una fila",
                "Selecciona un cliente/licencia en la tabla para copiar el mail.",
            )
            return

        nombre, _telefono, _duracion, caducidad, _restante, clave = values

        # Si es permanente o no hay fecha legible, no ponemos caducidad
        caducidad_text = ""
        if caducidad and str(caducidad).strip().lower() not in ("permanente", "null", "none", ""):
            caducidad_text = f"\nCaducidad: {caducidad}\n"

        subject = "Asunto: Tu licencia de SelectLive"
        body = (
            f"{subject}\n\n"
            f"Hola {nombre},\n"
            "Gracias por tu compra.\n\n"
            "Aquí tienes tu clave de licencia de SelectLive:\n\n"
            f"{clave}\n"
            f"{caducidad_text}\n"
            "Para activarla:\n"
            "1. Abre SelectLive\n"
            "2. Pulsa “Activar / cambiar licencia”\n"
            "3. Introduce la clave y confirma\n"
            "4. Reinicia el programa y listo\n\n"
            "Si necesitas ayuda con la instalación o el cambio de equipo, responde a este mensaje y te ayudamos.\n\n"
            "Un saludo,\n"
            "Equipo de SelectLive"
        )

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(body)
            self.root.update()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo copiar al portapapeles:\n{e}")
            return

        messagebox.showinfo("Copiado", "Texto del mail copiado al portapapeles.")

    def _extend_selected_license(self):
        if not self.admin_token:
            messagebox.showerror("Error", "ADMIN_TOKEN no está configurado.")
            return

        values = self._get_selected_row()
        if not values:
            messagebox.showwarning(
                "Selecciona una fila",
                "Selecciona un cliente/licencia en la tabla para añadir tiempo.",
            )
            return

        nombre, _telefono, _duracion, _caducidad, _restante, clave = values

        opciones = ["3 días", "1 mes", "3 meses", "6 meses", "12 meses", "Permanente"]
        duracion = simpledialog.askstring(
            "Añadir tiempo",
            "¿Cuánto tiempo quieres añadir?\n\n"
            f"Cliente: {nombre}\n"
            f"Clave: {clave}\n\n"
            "Opciones: 3 días / 1 mes / 3 meses / 6 meses / 12 meses / Permanente",
            parent=self.root,
        )
        if not duracion:
            return

        duracion = duracion.strip()
        if duracion not in opciones:
            messagebox.showerror(
                "Duración no válida",
                "Introduce exactamente una de estas opciones:\n"
                "3 días, 1 mes, 3 meses, 6 meses, 12 meses, Permanente",
            )
            return

        ok = messagebox.askyesno(
            "Confirmar",
            f"¿Añadir '{duracion}' a la licencia?\n\n{clave}",
            parent=self.root,
        )
        if not ok:
            return

        try:
            resp = requests.post(
                f"{self.base_url}/admin/extend_license/{clave}",
                json={"duration_label": duracion},
                headers={"X-Admin-Token": self.admin_token},
                timeout=10,
            )
        except Exception as e:
            messagebox.showerror("Error de conexión", f"No se pudo contactar con el servidor:\n{e}")
            return

        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            messagebox.showerror("Error", f"Código {resp.status_code}:\n{detail}")
            return

        self._refresh_clients()
        messagebox.showinfo("Renovada", "Tiempo añadido correctamente.")

    def _delete_selected_license(self):
        if not self.admin_token:
            messagebox.showerror(
                "Error de configuración",
                "ADMIN_TOKEN no está configurado.",
            )
            return

        license_key = self._get_selected_license_key()
        if not license_key:
            messagebox.showwarning(
                "Selecciona una fila",
                "Selecciona un cliente/licencia en la tabla para eliminarla.",
            )
            return

        ok = messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Seguro que quieres eliminar esta licencia?\n\n{license_key}\n\n"
            "Esto la borrará del servidor y dejará de funcionar en los clientes.",
        )
        if not ok:
            return

        try:
            resp = requests.delete(
                f"{self.base_url}/admin/license/{license_key}",
                headers={"X-Admin-Token": self.admin_token},
                timeout=10,
            )
        except Exception as e:
            messagebox.showerror(
                "Error de conexión",
                f"No se pudo contactar con el servidor:\n{e}",
            )
            return

        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            messagebox.showerror(
                "Error al eliminar",
                f"Código {resp.status_code}:\n{detail}",
            )
            return

        self._refresh_clients()
        messagebox.showinfo("Eliminada", "Licencia eliminada correctamente.")

    def _build_create_tab(self):
        form = tk.Frame(self.tab_create, bg="#101820")
        form.pack(pady=(10, 10))

        def label(text, r):
            tk.Label(
                form,
                text=text,
                font=("Segoe UI", 10),
                fg="#B0B0B0",
                bg="#101820",
                anchor="w",
                width=28,
            ).grid(row=r, column=0, sticky="w", padx=6, pady=6)

        label("Nombre:", 0)
        self.entry_name = tk.Entry(form, font=("Segoe UI", 10), width=35)
        self.entry_name.grid(row=0, column=1, padx=6, pady=6, sticky="w")

        label("Teléfono:", 1)
        self.entry_phone = tk.Entry(form, font=("Segoe UI", 10), width=35)
        self.entry_phone.grid(row=1, column=1, padx=6, pady=6, sticky="w")

        label("Duración licencia:", 2)
        self.duration_var = tk.StringVar(value="12 meses")
        options = ["3 días", "1 mes", "3 meses", "6 meses", "12 meses", "Permanente"]
        self.duration_menu = tk.OptionMenu(form, self.duration_var, *options)
        self.duration_menu.config(
            font=("Segoe UI", 10),
            bg="#151F2B",
            fg="#B0B0B0",
            activebackground="#1E90FF",
            activeforeground="white",
            relief="flat",
            highlightthickness=0,
            width=15,
        )
        self.duration_menu["menu"].config(
            bg="#151F2B",
            fg="#B0B0B0",
            activebackground="#1E90FF",
            activeforeground="white",
            relief="flat",
        )
        self.duration_menu.grid(row=2, column=1, padx=6, pady=6, sticky="w")

        # Botón crear
        btn_crear = tk.Button(
            self.tab_create,
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
        btn_crear.pack(pady=(5, 10))

        self.lbl_result = tk.Label(
            self.tab_create,
            text="Aquí aparecerá la clave de licencia generada.",
            font=("Segoe UI", 10, "bold"),
            fg="#B0B0B0",
            bg="#101820",
        )
        self.lbl_result.pack(pady=(5, 0))

    def _human_remaining(self, expires_at_iso: str | None) -> str:
        if not expires_at_iso:
            return "Permanente"
        try:
            # FastAPI suele devolver ISO con zona; lo normal es "...+00:00"
            dt = datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            return ""

        now = datetime.now(timezone.utc)
        delta = dt - now
        total_days = int(delta.total_seconds() // 86400)
        if total_days < 0:
            return "Caducada"

        months = total_days // 30
        days = total_days % 30

        parts = []
        if months > 0:
            parts.append(f"{months} mes" + ("es" if months != 1 else ""))
        parts.append(f"{days} día" + ("s" if days != 1 else ""))
        return " y ".join(parts)

    def _refresh_clients(self):
        if not self.admin_token:
            return
        try:
            resp = requests.get(
                f"{self.base_url}/admin/clients",
                headers={"X-Admin-Token": self.admin_token},
                timeout=10,
            )
        except Exception:
            return

        if resp.status_code != 200:
            return

        data = resp.json()

        # Cache + render (filtrable)
        self._clients_cache = []

        for row in data:
            name = row.get("customer_name") or ""
            phone = row.get("customer_phone") or ""
            duration = row.get("duration_label") or ""
            license_key = row.get("license_key") or ""
            expires_at = row.get("expires_at")
            is_expired = bool(row.get("is_expired"))

            caducidad = "Permanente"
            if expires_at:
                try:
                    dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    caducidad = dt.strftime("%d/%m/%Y")
                except Exception:
                    caducidad = str(expires_at)

            restante = "CADUCADO" if is_expired else self._human_remaining(expires_at)

            values = (name, phone, duration, caducidad, restante, license_key)
            tags = ("expired",) if is_expired else ()
            self._clients_cache.append((values, tags))

        self._apply_filter()

    def crear_licencia(self):
        # Validar ADMIN_TOKEN
        if not self.admin_token:
            messagebox.showerror(
                "Error de configuración",
                "ADMIN_TOKEN no está configurado.\n"
                "Configúralo en el archivo .env o como variable de entorno.",
            )
            return

        nombre = self.entry_name.get().strip()
        telefono = self.entry_phone.get().strip()
        duracion = self.duration_var.get().strip()

        if not nombre:
            messagebox.showerror("Dato requerido", "Introduce el nombre del cliente.")
            return
        if not telefono:
            messagebox.showerror("Dato requerido", "Introduce el teléfono del cliente.")
            return

        payload = {
            "max_devices": 1,
            "customer_name": nombre,
            "customer_phone": telefono,
            "duration_label": duracion,
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
        expires_at = data.get("expires_at")

        texto = f"Clave de licencia generada: {license_key}"
        if expires_at:
            texto += f"  (caduca: {expires_at})"
        self.lbl_result.config(text=texto)

        messagebox.showinfo(
            "Licencia creada",
            "Licencia creada correctamente.\n"
            "Copia la clave y entrégasela al cliente.",
        )

        # Refrescar clientes y limpiar campos
        self._refresh_clients()
        self.entry_name.delete(0, "end")
        self.entry_phone.delete(0, "end")
        self.duration_var.set("12 meses")


def main():
    root = tk.Tk()
    app = LicenseCreatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

