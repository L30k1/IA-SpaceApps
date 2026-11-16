import os
import socket
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog, ttk
from urllib.error import URLError
from urllib.request import urlopen


HOST = "127.0.0.1"
PORT = 5000
URL = f"http://{HOST}:{PORT}/"


def existing_server():
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            pass
    except OSError:
        return False

    try:
        with urlopen(URL, timeout=2) as response:
            if b"<title>MediSpace" in response.read(8192):
                return True
    except (OSError, URLError):
        pass
    raise RuntimeError("Another program is using port 5000. Close it and open MediSpace again.")


def launch():
    window = tk.Tk()
    window.title("MediSpace")
    window.withdraw()

    try:
        if existing_server():
            webbrowser.open(URL)
            window.destroy()
            return

        from werkzeug.serving import make_server

        from main import create_app
    except (RuntimeError, ImportError) as exc:
        if isinstance(exc, ImportError):
            messagebox.showerror(
                "MediSpace",
                "Python dependencies are missing. Run python -m pip install -r requirements.txt.",
                parent=window,
            )
        else:
            messagebox.showerror("MediSpace", str(exc), parent=window)
        window.destroy()
        return

    if not os.getenv("GEMINI_API_KEY"):
        key = simpledialog.askstring(
            "MediSpace",
            "Enter your AI key to enable checkups. Leave it blank to view the history.",
            show="*",
            parent=window,
        )
        if key is None:
            window.destroy()
            return
        if key.strip():
            os.environ["GEMINI_API_KEY"] = key.strip()

    try:
        server = make_server(HOST, PORT, create_app(), threaded=True)
    except (Exception, SystemExit) as exc:
        detail = "Check that port 5000 is available." if isinstance(exc, SystemExit) else str(exc)
        messagebox.showerror("MediSpace", f"MediSpace could not start.\n{detail}", parent=window)
        window.destroy()
        return

    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def stop():
        server.shutdown()
        worker.join()
        server.server_close()
        window.destroy()

    panel = ttk.Frame(window, padding=20)
    panel.grid()
    ttk.Label(panel, text="MediSpace is running").grid(pady=(0, 10))
    ttk.Button(panel, text="Open MediSpace", command=lambda: webbrowser.open(URL)).grid(sticky="ew")
    ttk.Button(panel, text="Stop MediSpace", command=stop).grid(sticky="ew", pady=(8, 0))
    window.protocol("WM_DELETE_WINDOW", stop)
    window.deiconify()
    window.after_idle(lambda: webbrowser.open(URL))
    window.mainloop()


if __name__ == "__main__":
    launch()
