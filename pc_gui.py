import socket
import threading
import time
import ctypes
from ctypes import wintypes

HOST = "0.0.0.0"
PORT = 5005

SPEED = 1.0
POSITION_UPDATE_RATE = 60

# ============================================================
# WINDOWS INPUT
# ============================================================

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)

    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


# ============================================================
# MOVE
# ============================================================

def move_mouse(dx, dy):
    dx = int(round(dx))
    dy = int(round(dy))

    if dx == 0 and dy == 0:
        return False

    extra = ctypes.pointer(wintypes.ULONG(0))

    mouse_input = MOUSEINPUT(
        dx=dx,
        dy=dy,
        mouseData=0,
        dwFlags=MOUSEEVENTF_MOVE,
        time=0,
        dwExtraInfo=extra,
    )

    input_data = INPUT(
        type=INPUT_MOUSE,
        u=INPUT_UNION(mi=mouse_input),
    )

    result = user32.SendInput(
        1,
        ctypes.byref(input_data),
        ctypes.sizeof(INPUT),
    )

    if result != 1:
        print(
            "SendInput error:",
            ctypes.get_last_error()
        )
        return False

    return True


# ============================================================
# BUTTON DOWN
# ============================================================

def mouse_button_down(button):
    if button == "left":
        flag = MOUSEEVENTF_LEFTDOWN
    elif button == "right":
        flag = MOUSEEVENTF_RIGHTDOWN
    else:
        return False

    extra = ctypes.pointer(wintypes.ULONG(0))

    input_data = INPUT(
        type=INPUT_MOUSE,
        u=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=flag,
                time=0,
                dwExtraInfo=extra,
            )
        ),
    )

    result = user32.SendInput(
        1,
        ctypes.byref(input_data),
        ctypes.sizeof(INPUT),
    )

    return result == 1


# ============================================================
# BUTTON UP
# ============================================================

def mouse_button_up(button):
    if button == "left":
        flag = MOUSEEVENTF_LEFTUP
    elif button == "right":
        flag = MOUSEEVENTF_RIGHTUP
    else:
        return False

    extra = ctypes.pointer(wintypes.ULONG(0))

    input_data = INPUT(
        type=INPUT_MOUSE,
        u=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=flag,
                time=0,
                dwExtraInfo=extra,
            )
        ),
    )

    result = user32.SendInput(
        1,
        ctypes.byref(input_data),
        ctypes.sizeof(INPUT),
    )

    return result == 1


# ============================================================
# CLICK
# ============================================================

def mouse_click(button):
    if button == "left":
        down = MOUSEEVENTF_LEFTDOWN
        up = MOUSEEVENTF_LEFTUP

    elif button == "right":
        down = MOUSEEVENTF_RIGHTDOWN
        up = MOUSEEVENTF_RIGHTUP

    else:
        return False

    extra = ctypes.pointer(wintypes.ULONG(0))

    down_input = INPUT(
        type=INPUT_MOUSE,
        u=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=down,
                time=0,
                dwExtraInfo=extra,
            )
        ),
    )

    up_input = INPUT(
        type=INPUT_MOUSE,
        u=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=up,
                time=0,
                dwExtraInfo=extra,
            )
        ),
    )

    result_down = user32.SendInput(
        1,
        ctypes.byref(down_input),
        ctypes.sizeof(INPUT),
    )

    result_up = user32.SendInput(
        1,
        ctypes.byref(up_input),
        ctypes.sizeof(INPUT),
    )

    return result_down == 1 and result_up == 1


# ============================================================
# SCROLL
# ============================================================

WHEEL_DELTA = 120
scroll_remainder = 0.0


def scroll_mouse(amount):
    global scroll_remainder

    scroll_remainder += amount

    steps = int(scroll_remainder)

    if steps == 0:
        return False

    scroll_remainder -= steps

    wheel_amount = steps * WHEEL_DELTA

    extra = ctypes.pointer(wintypes.ULONG(0))

    wheel_input = INPUT(
        type=INPUT_MOUSE,
        u=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=wheel_amount,
                dwFlags=MOUSEEVENTF_WHEEL,
                time=0,
                dwExtraInfo=extra,
            )
        ),
    )

    result = user32.SendInput(
        1,
        ctypes.byref(wheel_input),
        ctypes.sizeof(INPUT),
    )

    return result == 1


# ============================================================
# NETWORK
# ============================================================

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

sock.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1
)

sock.bind(
    (HOST, PORT)
)

phone_address = None

address_lock = threading.Lock()

running = True


# ============================================================
# CURSOR POSITION
# ============================================================

def get_cursor_position():
    point = wintypes.POINT()

    result = user32.GetCursorPos(
        ctypes.byref(point)
    )

    if result == 0:
        return 0, 0

    return point.x, point.y


def get_screen_size():
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)

    return width, height


# ============================================================
# CURSOR POSITION THREAD
# ============================================================

def send_cursor_position():
    global phone_address

    interval = 1.0 / POSITION_UPDATE_RATE

    next_time = time.perf_counter()

    while running:

        try:

            with address_lock:
                current_phone = phone_address

            if current_phone is not None:

                x, y = get_cursor_position()

                width, height = get_screen_size()

                message = (
                    f"POS,{x},{y},{width},{height}"
                )

                sock.sendto(
                    message.encode("utf-8"),
                    current_phone
                )

        except Exception as e:

            print(
                "Position update error:",
                e
            )

        next_time += interval

        remaining = (
            next_time -
            time.perf_counter()
        )

        if remaining > 0:

            time.sleep(remaining)

        else:

            next_time = time.perf_counter()


position_thread = threading.Thread(
    target=send_cursor_position,
    daemon=True
)

position_thread.name = "CursorPositionThread"

position_thread.start()


# ============================================================
# STARTUP
# ============================================================

print()
print("================================================")
print("       ONLINE MOUSE - NATIVE WINDOWS")
print("================================================")
print()

print(f"UDP Port       : {PORT}")
print(f"Position Rate  : {POSITION_UPDATE_RATE} Hz")
print(f"Mouse Speed    : {SPEED}")
print("Input Method   : Windows SendInput")
print("Latency Test   : ISOLATED")
print()

print("Waiting for Android phone...")
print()


# ============================================================
# MAIN RECEIVER LOOP
# ============================================================

try:

    while True:

        data, address = sock.recvfrom(2048)

        try:

            message = data.decode(
                "utf-8"
            ).strip()
            

        except UnicodeDecodeError:

            print(
                "Invalid data received from:",
                address
            )

            continue
        
        # Automatic PC discovery
        if message == "DISCOVER_ONLINEMOUSE":
            try:
                sock.sendto(
                    b"DISCOVERED_ONLINEMOUSE",
                    address
                )
                print(
                    f"PC discovery response sent to {address[0]}"
                )
            except OSError as exc:
                print("Discovery response failed:", exc)

            continue

        # ====================================================
        # PING
        # ====================================================

        if message.startswith("PING,"):

            token = message[5:]

            sock.sendto(
                f"PONG,{token}".encode("utf-8"),
                address
            )

            continue

        # ====================================================
        # HELLO
        # ====================================================

        if message == "HELLO":

            new_connection = False

            with address_lock:

                if phone_address != address:

                    phone_address = address

                    new_connection = True

            if new_connection:

                print()
                print(
                    "--------------------------------------------"
                )
                print("PHONE CONNECTED")
                print(
                    "Phone IP   :",
                    address[0]
                )
                print(
                    "Phone Port :",
                    address[1]
                )
                print(
                    "--------------------------------------------"
                )
                print()

            sock.sendto(
                b"PONG",
                address
            )

            x, y = get_cursor_position()

            width, height = get_screen_size()

            position_message = (
                f"POS,{x},{y},{width},{height}"
            )

            sock.sendto(
                position_message.encode("utf-8"),
                address
            )

            continue

        # ====================================================
        # MOVE
        # ====================================================

        if message.startswith("MOVE,"):

            parts = message.split(",")

            # Normal current Android format:
            #
            # MOVE,dx,dy
            #
            if len(parts) == 3:

                try:

                    dx = float(parts[1])
                    dy = float(parts[2])

                    dx *= SPEED
                    dy *= SPEED

                    move_mouse(
                        dx,
                        dy
                    )

                except ValueError:

                    print(
                        "Invalid MOVE command:",
                        message
                    )

                continue

            # Optional instrumented format:
            #
            # MOVE,sequence,dx,dy
            #
            # IMPORTANT:
            # No ACK is generated here.
            # This keeps the normal movement path clean.

            if len(parts) == 4:

                try:

                    dx = float(parts[2])
                    dy = float(parts[3])

                    dx *= SPEED
                    dy *= SPEED

                    move_mouse(
                        dx,
                        dy
                    )

                except ValueError:

                    print(
                        "Invalid MOVE command:",
                        message
                    )

                continue

            print(
                "Invalid MOVE command:",
                message
            )

            continue

        # ====================================================
        # LEFT DOWN
        # ====================================================

        if message == "LEFT_DOWN":

            mouse_button_down("left")

            continue

        # ====================================================
        # LEFT UP
        # ====================================================

        if message == "LEFT_UP":

            mouse_button_up("left")

            continue

        # ====================================================
        # LEFT CLICK
        # ====================================================

        if message == "CLICK_LEFT":

            mouse_click("left")

            continue

        # ====================================================
        # RIGHT CLICK
        # ====================================================

        if message == "CLICK_RIGHT":

            mouse_click("right")

            continue

        # ====================================================
        # SCROLL
        # ====================================================

        if message.startswith("SCROLL,"):

            parts = message.split(",")

            if len(parts) == 2:

                try:

                    amount = float(parts[1])

                    scroll_mouse(
                        amount
                    )

                except ValueError:

                    print(
                        "Invalid SCROLL command:",
                        message
                    )

            continue

        # ====================================================
        # UNKNOWN COMMAND
        # ====================================================

        if message != "":

            print(
                "Unknown command:",
                message
            )


# ============================================================
# STOP
# ============================================================

except KeyboardInterrupt:

    print()
    print(
        "Stopping Online Mouse Receiver..."
    )


finally:

    running = False

    with address_lock:
        phone_address = None

    try:
        sock.close()
    except Exception:
        pass

    print(
        "Receiver stopped."
    )
