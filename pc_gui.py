import os
import re
import socket
import subprocess
import sys
import threading
import queue
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

# Online Mouse - Windows PC GUI (QR pairing removed)
APP_DIR = Path(__file__).resolve().parent
RECEIVER_FILE = APP_DIR / "receiver2.py"
PORT = 5005

BG = "#0B0F14"
PANEL = "#141B24"
CYAN = "#36D9FF"
GREEN = "#45E39A"
RED = "#FF647C"
TEXT = "#F0F5FA"
MUTED = "#9BAAB8"

process = None
log_queue = queue.Queue()


def get_local_ip():
    """Find a usable local IPv4 address, preferring the Wi-Fi adapter."""
    try:
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
        current_adapter = ""
        fallback_ip = None
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
                if any(name in current_adapter for name in ("wi-fi", "wireless", "wlan")):
                    return ip
        return fallback_ip or "IP not found"
    except (OSError, subprocess.SubprocessError):
        return "IP detection failed"


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
            "A valid PC IP address was not found. Check that the PC is connected to Wi-Fi.",
        )
        return
    root.clipboard_clear()
    root.clipboard_append(ip)
    root.update()
    add_log(f"Copied PC IP: {ip}")


def read_receiver_output(proc):
    try:
        if proc.stdout is not None:
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if line:
                    add_log(line)
    except (OSError, ValueError) as error:
        add_log(f"Could not read receiver output: {error}")


def start_server():
    global process
    if process is not None and process.poll() is None:
        messagebox.showinfo("Online Mouse", "Receiver is already running.")
        return
    if not RECEIVER_FILE.is_file():
        messagebox.showerror(
            "Receiver file not found",
            "receiver2.py is missing.\n\nKeep pc_gui.py and receiver2.py in the same folder.",
        )
        return
    try:
        process = subprocess.Popen(
            [sys.executable, "-u", str(RECEIVER_FILE)],
            cwd=str(APP_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        threading.Thread(
            target=read_receiver_output, args=(process,), daemon=True
        ).start()
        status_label.config(text="● RECEIVER STARTED", fg=GREEN)
        add_log("Starting receiver2.py...")
        add_log("Started means the process launched, not that the phone connected.")
    except OSError as error:
        process = None
        status_label.config(text="● RECEIVER FAILED TO START", fg=RED)
        messagebox.showerror("Could not start receiver", str(error))


def stop_server():
    global process
    if process is None or process.poll() is not None:
        status_label.config(text="● RECEIVER STOPPED", fg=RED)
        add_log("Receiver is not running.")
        return
    try:
        process.terminate()
        status_label.config(text="● STOP REQUESTED", fg=RED)
        add_log("Stop requested for receiver2.py.")
    except OSError as error:
        messagebox.showerror("Could not stop receiver", str(error))


def refresh_ui():
    global process
    refresh_log()
    if process is not None and process.poll() is not None:
        exit_code = process.returncode
        status_label.config(text="● RECEIVER STOPPED", fg=RED)
        add_log(f"Receiver exited with code {exit_code}.")
        process = None
    root.after(150, refresh_ui)


def close_app():
    global process
    if process is not None and process.poll() is None:
        should_close = messagebox.askyesno(
            "Exit Online Mouse",
            "The receiver is running. Stop it and exit?",
        )
        if not should_close:
            return
        try:
            process.terminate()
        except OSError:
            pass
    root.destroy()


# Main window
root = tk.Tk()
root.title("Online Mouse | PC Controller")
root.geometry("760x650")
root.minsize(650, 570)
root.configure(bg=BG)
root.protocol("WM_DELETE_WINDOW", close_app)

header = tk.Frame(root, bg=BG)
header.pack(fill="x", padx=24, pady=(22, 12))
tk.Label(
    header, text="ONLINE MOUSE", font=("Segoe UI", 23, "bold"),
    fg=CYAN, bg=BG,
).pack(anchor="w")
tk.Label(
    header, text="GAMING PC MOUSE CONTROLLER",
    font=("Segoe UI", 9, "bold"), fg=MUTED, bg=BG,
).pack(anchor="w", pady=(3, 0))

panel = tk.Frame(root, bg=PANEL, padx=18, pady=16)
panel.pack(fill="x", padx=24, pady=8)
tk.Label(
    panel, text="PC CONNECTION DETAILS", font=("Segoe UI", 10, "bold"),
    fg=TEXT, bg=PANEL,
).pack(anchor="w")

ip_row = tk.Frame(panel, bg=PANEL)
ip_row.pack(fill="x", pady=(12, 6))
tk.Label(
    ip_row, text="PC IPv4 Address:", font=("Segoe UI", 10),
    fg=MUTED, bg=PANEL,
).pack(side="left")
ip_value = tk.Label(
    ip_row, text=get_local_ip(), font=("Consolas", 12, "bold"),
    fg=CYAN, bg=PANEL,
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
    panel, text=f"UDP Port: {PORT}", font=("Segoe UI", 10),
    fg=MUTED, bg=PANEL,
).pack(anchor="w", pady=(4, 0))

status_label = tk.Label(
    root, text="● RECEIVER STOPPED", font=("Segoe UI", 11, "bold"),
    fg=RED, bg=BG,
)
status_label.pack(anchor="w", padx=26, pady=(12, 8))

buttons = tk.Frame(root, bg=BG)
buttons.pack(fill="x", padx=24, pady=(0, 14))
tk.Button(
    buttons, text="▶  Start Receiver", command=start_server,
    bg=CYAN, fg="#071017", activebackground="#76E6FF",
    activeforeground="#071017", relief="flat", font=("Segoe UI", 10, "bold"),
    padx=18, pady=10, cursor="hand2",
).pack(side="left", padx=(0, 10))
tk.Button(
    buttons, text="■  Stop Receiver", command=stop_server,
    bg="#3A2029", fg="#FFB7C3", activebackground="#57303B",
    activeforeground=TEXT, relief="flat", font=("Segoe UI", 10, "bold"),
    padx=18, pady=10, cursor="hand2",
).pack(side="left")

tk.Label(
    root, text="RECEIVER LOG", font=("Segoe UI", 9, "bold"),
    fg=MUTED, bg=BG,
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

add_log("Online Mouse PC GUI ready.")
add_log("Receiver will start automatically.")
add_log("Phone and PC should be connected to the same Wi-Fi network.")
add_log("Use the PC IPv4 address shown above for manual setup if needed.")

root.after(150, refresh_ui)
root.after(800, start_server)
root.mainloop()
