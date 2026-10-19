import os
import re
import socket
import subprocess
import sys
import threading
import queue
import time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

# ============================================================
# APP DIR + RECEIVER FILE
# ============================================================

if getattr(sys, "frozen", False):
    APP_DIR       = Path(sys.executable).resolve().parent
    RECEIVER_FILE = APP_DIR / "receiver2.exe"
else:
    APP_DIR       = Path(__file__).resolve().parent
    RECEIVER_FILE = APP_DIR / "receiver2.py"

PORT = 5005

# ============================================================
# COLORS
# ============================================================

BG    = "#0B0F14"
PANEL = "#141B24"
CYAN  = "#36D9FF"
GREEN = "#45E39A"
RED   = "#FF647C"
TEXT  = "#F0F5FA"
MUTED = "#9BAAB8"

# ============================================================
# STATE
# ============================================================

process            = None
_receiver_stopping = False
log_queue          = queue.Queue()

# ============================================================
# FIREWALL AUTO FIX
# ============================================================


def auto_fix_firewall():
    try:
        check = subprocess.run(
            [
                "netsh", "advfirewall", "firewall",
                "show", "rule", "name=OnlineMouse", "dir=in", "verbose"
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        rule_exists = (
            "Rule Name:" in check.stdout
            and "OnlineMouse" in check.stdout
        )

        if rule_exists:
            result = subprocess.run(
                [
                    "netsh", "advfirewall", "firewall",
                    "set", "rule", "name=OnlineMouse", "new",
                    "profile=private",
                    "remoteip=LocalSubnet",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        else:
            result = subprocess.run(
                [
                    "netsh", "advfirewall", "firewall",
                    "add", "rule",
                    "name=OnlineMouse",
                    "dir=in",
                    "action=allow",
                    "enable=yes",
                    "profile=private",
                    "protocol=UDP",
                    f"localport={PORT}",
                    "remoteip=LocalSubnet",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        if result.returncode == 0:
            add_log(
                "Firewall rule configured for Private network "
                "and LocalSubnet."
            )
            return True

        details = (result.stdout + "\n" + result.stderr).strip()
        add_log(f"Firewall update failed: {details}")
        add_log(
            "If permission is denied, close the app and run "
            "pc_gui.exe as administrator."
        )
        return False

    except (OSError, subprocess.SubprocessError) as error:
        add_log(f"Firewall check failed: {error}")
        return False

# ============================================================
# IP DETECTION
# ============================================================

def get_local_ip():
    try:
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
        current_adapter = ""
        fallback_ip     = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if line and not line[0].isspace() and ":" in stripped:
                current_adapter = stripped.lower()
            if re.search(r"ipv4 address", stripped, re.IGNORECASE):
                match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", stripped)
                if not match:
                    continue
                ip = match.group(1)
                try:
                    socket.inet_aton(ip)
                except OSError:
                    continue
                if ip.startswith(("127.", "169.254.")):
                    continue
                if fallback_ip is None:
                    fallback_ip = ip
                if any(n in current_adapter for n in ("wi-fi", "wireless", "wlan")):
                    return ip
        return fallback_ip or "IP not found"
    except (OSError, subprocess.SubprocessError):
        return "IP detection failed"

# ============================================================
# LOG
# ============================================================

def add_log(message):
    log_queue.put(str(message))

def refresh_log():
    while True:
        try:
            line = log_queue.get_nowait()
        except queue.Empty:
            break
        log_text.config(state="normal")
        log_text.insert("end", line + "\n")
        log_text.see("end")
        log_text.config(state="disabled")

def refresh_ip():
    ip = get_local_ip()
    ip_value.config(text=ip)
    add_log(f"IP refreshed: {ip}")

def copy_ip():
    ip = ip_value.cget("text")
    if ip in ("IP not found", "IP detection failed", "Not available", ""):
        messagebox.showwarning(
            "IP unavailable",
            "Valid PC IP nahi mila. Check karo PC WiFi se connected hai.",
        )
        return
    root.clipboard_clear()
    root.clipboard_append(ip)
    root.update()
    add_log(f"Copied: {ip}")

# ============================================================
# RECEIVER OUTPUT READER
# ============================================================

def read_receiver_output(proc):
    try:
        if proc.stdout is not None:
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if line:
                    add_log(line)
    except (OSError, ValueError) as error:
        add_log(f"Output read error: {error}")
    finally:
        # Sirf tab restart karo jab unexpected crash ho
        if not _receiver_stopping and proc is process:
            add_log("⚠️  Receiver unexpected stop — 3s mein restart hoga...")
            time.sleep(3)
            root.after(0, start_server)

# ============================================================
# START SERVER
# FIX: Dono modes mein CREATE_NO_WINDOW use karo
#      Lekin STARTUPINFO se window hide karo — stdout pipe bhi kaam karega
# ============================================================

def _make_popen_kwargs(cmd):
    """
    Windows pe CMD window hide karo lekin stdout pipe karte raho.
    STARTUPINFO use karo — CREATE_NO_WINDOW EXE stdout todta hai.
    """
    kwargs = dict(
        cwd=str(APP_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    if os.name == "nt":
        # STARTUPINFO se window hide hogi
        # stdout pipe bhi sahi kaam karega
        si = subprocess.STARTUPINFO()
        si.dwFlags    |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
        # CREATE_NO_WINDOW bilkul mat lagao EXE ke liye
        kwargs["creationflags"] = 0

    return kwargs


def start_server():
    global process, _receiver_stopping
    _receiver_stopping = False

    # Double-call guard
    if process is not None and process.poll() is None:
        return

    if not RECEIVER_FILE.is_file():
        msg = (
            f"{RECEIVER_FILE.name} nahi mila.\n\n"
            "Dono files ek hi folder mein rakho:\n"
            "  • OnlineMouse.exe\n"
            "  • receiver2.exe"
        )
        messagebox.showerror("File not found", msg)
        add_log(f"❌ {RECEIVER_FILE.name} nahi mila: {RECEIVER_FILE}")
        return

    auto_fix_firewall()

    try:
        if getattr(sys, "frozen", False):
            # EXE mode — receiver2.exe directly
            cmd = [str(RECEIVER_FILE)]
        else:
            # Python development mode
            cmd = [sys.executable, "-u", str(RECEIVER_FILE)]

        kwargs  = _make_popen_kwargs(cmd)
        process = subprocess.Popen(cmd, **kwargs)

        threading.Thread(
            target=read_receiver_output,
            args=(process,),
            daemon=True,
        ).start()

        status_label.config(text="● RECEIVER STARTED", fg=GREEN)
        add_log("✅ receiver2 start ho gaya.")
        add_log("Phone aur PC ek hi WiFi pe hone chahiye.")

    except OSError as error:
        process = None
        status_label.config(text="● START FAILED", fg=RED)
        add_log(f"❌ Start failed: {error}")
        messagebox.showerror("Start nahi ho saka", str(error))

# ============================================================
# STOP SERVER
# ============================================================

def stop_server():
    global process, _receiver_stopping
    _receiver_stopping = True

    if process is None or process.poll() is not None:
        status_label.config(text="● RECEIVER STOPPED", fg=RED)
        add_log("Receiver chal nahi raha.")
        return
    try:
        process.terminate()
        status_label.config(text="● RECEIVER STOPPED", fg=RED)
        add_log("Receiver band kar diya.")
    except OSError as error:
        messagebox.showerror("Stop nahi ho saka", str(error))

# ============================================================
# UI REFRESH LOOP
# ============================================================

def refresh_ui():
    global process
    refresh_log()
    if process is not None and process.poll() is not None:
        if not _receiver_stopping:
            status_label.config(text="● RECEIVER CRASHED", fg=RED)
            add_log(f"Receiver crash — code {process.returncode}.")
        else:
            status_label.config(text="● RECEIVER STOPPED", fg=RED)
        process = None
    root.after(150, refresh_ui)

# ============================================================
# CLOSE
# ============================================================

def close_app():
    global process
    if process is not None and process.poll() is None:
        if not messagebox.askyesno(
            "Exit", "Receiver chal raha hai. Band karke exit karein?"
        ):
            return
        try:
            process.terminate()
        except OSError:
            pass
    root.destroy()

# ============================================================
# MAIN WINDOW
# ============================================================

root = tk.Tk()
root.title("Online Mouse | PC Controller")
root.geometry("760x650")
root.minsize(650, 570)
root.configure(bg=BG)
root.protocol("WM_DELETE_WINDOW", close_app)

# Header
header = tk.Frame(root, bg=BG)
header.pack(fill="x", padx=24, pady=(22, 12))
tk.Label(
    header, text="ONLINE MOUSE",
    font=("Segoe UI", 23, "bold"), fg=CYAN, bg=BG,
).pack(anchor="w")
tk.Label(
    header, text="GAMING PC MOUSE CONTROLLER",
    font=("Segoe UI", 9, "bold"), fg=MUTED, bg=BG,
).pack(anchor="w", pady=(3, 0))

# IP Panel
panel = tk.Frame(root, bg=PANEL, padx=18, pady=16)
panel.pack(fill="x", padx=24, pady=8)
tk.Label(
    panel, text="PC CONNECTION DETAILS",
    font=("Segoe UI", 10, "bold"), fg=TEXT, bg=PANEL,
).pack(anchor="w")
ip_row = tk.Frame(panel, bg=PANEL)
ip_row.pack(fill="x", pady=(12, 6))
tk.Label(
    ip_row, text="PC IPv4 Address:",
    font=("Segoe UI", 10), fg=MUTED, bg=PANEL,
).pack(side="left")
ip_value = tk.Label(
    ip_row, text=get_local_ip(),
    font=("Consolas", 12, "bold"), fg=CYAN, bg=PANEL,
)
ip_value.pack(side="left", padx=(8, 12))
tk.Button(
    ip_row, text="Refresh IP", command=refresh_ip,
    bg="#243442", fg=TEXT, activebackground="#30495C",
    activeforeground=TEXT, relief="flat", padx=10, pady=5, cursor="hand2",
).pack(side="right", padx=(6, 0))
tk.Button(
    ip_row, text="Copy IP", command=copy_ip,
    bg="#243442", fg=TEXT, activebackground="#30495C",
    activeforeground=TEXT, relief="flat", padx=10, pady=5, cursor="hand2",
).pack(side="right")
tk.Label(
    panel, text=f"UDP Port: {PORT}",
    font=("Segoe UI", 10), fg=MUTED, bg=PANEL,
).pack(anchor="w", pady=(4, 0))

# Status
status_label = tk.Label(
    root, text="● RECEIVER STOPPED",
    font=("Segoe UI", 11, "bold"), fg=RED, bg=BG,
)
status_label.pack(anchor="w", padx=26, pady=(12, 8))

# Buttons
buttons = tk.Frame(root, bg=BG)
buttons.pack(fill="x", padx=24, pady=(0, 14))
tk.Button(
    buttons, text="▶  Start Receiver", command=start_server,
    bg=CYAN, fg="#071017", activebackground="#76E6FF",
    activeforeground="#071017", relief="flat",
    font=("Segoe UI", 10, "bold"), padx=18, pady=10, cursor="hand2",
).pack(side="left", padx=(0, 10))
tk.Button(
    buttons, text="■  Stop Receiver", command=stop_server,
    bg="#3A2029", fg="#FFB7C3", activebackground="#57303B",
    activeforeground=TEXT, relief="flat",
    font=("Segoe UI", 10, "bold"), padx=18, pady=10, cursor="hand2",
).pack(side="left")

# Log
tk.Label(
    root, text="RECEIVER LOG",
    font=("Segoe UI", 9, "bold"), fg=MUTED, bg=BG,
).pack(anchor="w", padx=26, pady=(4, 6))
log_frame = tk.Frame(root, bg=PANEL)
log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 22))
scrollbar = tk.Scrollbar(log_frame)
scrollbar.pack(side="right", fill="y")
log_text = tk.Text(
    log_frame, bg=PANEL, fg="#C9D7E5", insertbackground=TEXT,
    font=("Consolas", 9), relief="flat", wrap="word",
    yscrollcommand=scrollbar.set, padx=10, pady=10, state="disabled",
)
log_text.pack(side="left", fill="both", expand=True)
scrollbar.config(command=log_text.yview)

# Startup logs
add_log("Online Mouse PC GUI ready.")
add_log("Receiver will start automatically.")
add_log("Phone and PC should be connected to the same Wi-Fi network.")
add_log(f"PC IP: {get_local_ip()}  ← Phone mein yahi daalo")

root.after(150, refresh_ui)
root.after(800, start_server)
root.mainloop()
