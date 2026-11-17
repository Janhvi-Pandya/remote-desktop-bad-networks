# measure.py: measures input delay by speaking the VNC protocol (RFB) directly.
#
# Run it INSIDE the client namespace:
#   sudo ip netns exec client python3 measure.py LABEL TRIALS
#   e.g. sudo ip netns exec client python3 measure.py delay50 100   -> results/delay50.csv
#
# What one trial does:
#   1. send a KeyEvent ("space" pressed + released) to the server, start the stopwatch
#   2. the key travels over the veth link (netem adds delay/loss here)
#   3. flip.py on the server flips the square, the server encodes the change
#   4. the FramebufferUpdate travels back over the link (netem again)
#   5. we read the update, see the square changed colour, stop the stopwatch
# So we measure exactly: network both ways + server work. Nothing on Windows is involved.

import socket, struct, sys, time, random, csv, os

label  = sys.argv[1] if len(sys.argv) > 1 else "test"
trials = int(sys.argv[2]) if len(sys.argv) > 2 else 20
WARMUP  = 3           # first few trials are thrown away (like the slow first ping)
TIMEOUT = 10.0        # give up on one trial after 10 s and count it as missing

SERVER = ("10.0.0.1", 5901)
SPACE  = 0x20         # the X "keysym" code for the space bar

# ---------- small helpers for reading exact numbers of bytes ----------

def recv_exact(sock, n):
    # TCP is a stream: one recv() may return fewer bytes than asked, so loop until we have n
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("server closed the connection")
        data += chunk
    return data

# ---------- 1. connect and do the RFB handshake ----------

sock = socket.create_connection(SERVER)
sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # send small messages immediately, no batching

server_version = recv_exact(sock, 12)        # server says e.g. b"RFB 003.008\n"
sock.sendall(b"RFB 003.008\n")               # we answer with the same version

n_types = recv_exact(sock, 1)[0]             # server lists the security types it allows
types = recv_exact(sock, n_types)
if 1 not in types:                           # type 1 = "None" (no password)
    sys.exit("Server needs a password. Run the latest setup.sh (it starts Xvnc with -SecurityTypes None).")
sock.sendall(b"\x01")                        # choose "None"
if struct.unpack(">I", recv_exact(sock, 4))[0] != 0:   # 0 = OK
    sys.exit("Security handshake failed")

sock.sendall(b"\x01")                        # ClientInit: 1 = shared, so the normal viewer can stay connected too
width, height = struct.unpack(">HH", recv_exact(sock, 4))   # ServerInit: screen size...
recv_exact(sock, 16)                         # ...the server's pixel format (we replace it next)
name_len = struct.unpack(">I", recv_exact(sock, 4))[0]
recv_exact(sock, name_len)                   # ...and the desktop name

# SetPixelFormat (message type 0): 32 bits per pixel, true colour, 8 bits each for R, G, B
sock.sendall(struct.pack(">B3x BBBB HHH BBB 3x", 0,
                         32, 24, 0, 1,        # bits-per-pixel, depth, big-endian=no, true-colour=yes
                         255, 255, 255,       # max value of red, green, blue
                         16, 8, 0))           # bit position of red, green, blue in each pixel

# SetEncodings (message type 2): only "Raw" (encoding 0) = plain pixels, easy to read
sock.sendall(struct.pack(">BxH i", 2, 1, 0))

# The square from flip.py is 100x100 in the centre of the screen. We watch a 10x10 patch inside it,
# up and to the left of the exact centre, because the server draws the mouse pointer at the centre
# of the screen and that would hide the square's colour.
PX, PY, PW, PH = width // 2 - 40, height // 2 - 40, 10, 10

def request_update(incremental):
    # FramebufferUpdateRequest (type 3): "send me this rectangle"
    # incremental=1 means "only when it changes", 0 means "right now"
    sock.sendall(struct.pack(">BB HHHH", 3, incremental, PX, PY, PW, PH))

def send_key():
    # KeyEvent (type 4): down=1 then down=0 (press and release)
    sock.sendall(struct.pack(">BBxx I", 4, 1, SPACE) + struct.pack(">BBxx I", 4, 0, SPACE))

def read_patch_colour():
    # Read server messages until a FramebufferUpdate covering our patch arrives.
    # Returns the colour of the patch's centre pixel as (R, G, B).
    while True:
        msg_type = recv_exact(sock, 1)[0]
        if msg_type == 0:                                         # FramebufferUpdate
            recv_exact(sock, 1)                                   # padding
            n_rects = struct.unpack(">H", recv_exact(sock, 2))[0]
            colour = None
            for _ in range(n_rects):
                x, y, w, h, enc = struct.unpack(">HHHHi", recv_exact(sock, 12))
                if enc != 0:
                    sys.exit(f"unexpected encoding {enc}")
                pixels = recv_exact(sock, w * h * 4)              # raw pixels, 4 bytes each
                cx, cy = PX + PW // 2, PY + PH // 2               # centre of our patch
                if x <= cx < x + w and y <= cy < y + h:
                    i = ((cy - y) * w + (cx - x)) * 4
                    b, g, r = pixels[i], pixels[i + 1], pixels[i + 2]   # little-endian: blue, green, red, unused
                    colour = (r, g, b)
            if colour is not None:
                return colour
        elif msg_type == 2:                                       # Bell: no extra data
            continue
        elif msg_type == 3:                                       # ServerCutText (clipboard): skip it
            recv_exact(sock, 3)
            recv_exact(sock, struct.unpack(">I", recv_exact(sock, 4))[0])
        else:
            sys.exit(f"unexpected server message type {msg_type}")

# ---------- 2. find the starting colour ----------

request_update(0)
current = read_patch_colour()
if current not in [(0, 0, 0), (255, 255, 255)]:
    sys.exit(f"Centre colour is {current}, not black or white. Is flip.py running?")

# ---------- 3. self-check: one key press should flip the square ----------

sock.settimeout(TIMEOUT)
send_key(); request_update(1)
try:
    new = read_patch_colour()
except socket.timeout:
    sys.exit("SELF-CHECK FAILED: no screen change after a key press. Is flip.py running and focused?")
current = new
print(f"Self-check OK. Measuring '{label}': {trials} trials (+{WARMUP} warm-up)...")

# ---------- 4. the real measurements ----------

os.makedirs("results", exist_ok=True)
path = f"results/{label}.csv"
times = []
with open(path, "w", newline="") as f:
    out = csv.writer(f)
    out.writerow(["condition", "trial", "latency_ms"])
    for i in range(trials + WARMUP):
        t0 = time.perf_counter()                      # start the stopwatch
        send_key()                                    # key goes out over the network
        request_update(1)                             # "tell me when the square changes"
        ms = None
        try:
            while True:
                colour = read_patch_colour()
                if colour != current:                 # the square changed: the round trip is complete
                    ms = (time.perf_counter() - t0) * 1000
                    current = colour
                    break
                request_update(1)                     # got an update but no change yet, keep waiting
        except socket.timeout:
            print(f"  trial {i + 1}: no change within {TIMEOUT} s, recorded as missing")
            break                                     # the connection is in an unknown state, stop here
        if i >= WARMUP:
            out.writerow([label, i - WARMUP + 1, "" if ms is None else round(ms, 2)])
            if ms is not None:
                times.append(ms)
        time.sleep(random.uniform(0.2, 0.4))          # random pause between trials

times.sort()
if times:
    n = len(times)
    print(f"{label}: {n} ok, median {times[n // 2]:.1f} ms, "
          f"p90 {times[int(n * 0.9)]:.1f}, min {times[0]:.1f}, max {times[-1]:.1f}  -> saved {path}")
else:
    print(f"{label}: no successful trials")
