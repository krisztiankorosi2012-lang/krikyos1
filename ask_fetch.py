# Minimal HTTPS ask after reboot — max free heap (no games / wifi UI loaded).
# Writes answers for questions saved in ask.q by wifi.browse.

import gc
import time

ASK_Q = "ask.q"
HOST = "krikymachine.vercel.app"
PORT = 443
LIMIT = 240
CFG = "wifi.cfg"


def _cx(oled, s, y, c=1):
    oled.text(s, max(0, (128 - len(s) * 8) // 2), y, c)


def _load(oled, title, note="", pct=0):
    oled.fill(0)
    _cx(oled, title[:16], 6)
    if note:
        _cx(oled, note[:16], 20)
    oled.rect(14, 36, 100, 12, 1)
    w = int(96 * pct / 100)
    if w > 0:
        oled.fill_rect(16, 38, min(96, w), 8, 1)
    oled.text("%d%%" % int(pct), 52, 52)
    oled.show()


def _show(oled, buttons, title, text):
    words = (text or "?").replace("\n", " ").split()
    lines = []
    cur = ""
    for w in words:
        if len(cur) + 1 + len(w) <= 16:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            while len(w) > 16:
                lines.append(w[:16])
                w = w[16:]
            cur = w
    if cur:
        lines.append(cur)
    if not lines:
        lines = ["?"]
    top = 0
    while True:
        oled.fill(0)
        oled.fill_rect(0, 0, 128, 11, 1)
        _cx(oled, title[:16], 2, 0)
        y = 14
        for line in lines[top:top + 4]:
            oled.text(line, 0, y)
            y += 12
        oled.text("2 OK", 48, 55)
        oled.show()
        buttons.update()
        if buttons.press(1) or buttons.press(0):
            return
        if buttons.press(2):
            top = 0 if top + 4 >= len(lines) else top + 1
        time.sleep_ms(12)


def _enc(s):
    out = []
    for c in s:
        o = ord(c)
        if (48 <= o <= 57) or (65 <= o <= 90) or (97 <= o <= 122) or c in "-._":
            out.append(c)
        elif c == " ":
            out.append("+")
        else:
            out.append("%%%02X" % o)
    return "".join(out)


def _ascii(s):
    out = []
    for c in s:
        o = ord(c)
        if 32 <= o < 127:
            out.append(c)
    return "".join(out).strip()


def _cfg():
    try:
        with open(CFG, "r") as f:
            lines = f.read().replace("\r", "").split("\n")
        ssid = lines[0].strip() if lines else ""
        pwd = lines[1].strip("\r") if len(lines) > 1 else ""
        if ssid:
            return ssid, pwd
    except Exception:
        pass
    return None, None


def _connect(oled):
    import network
    gc.collect()
    try:
        network.WLAN(network.AP_IF).active(False)
    except Exception:
        pass
    ssid, pwd = _cfg()
    if not ssid:
        return False, "no wifi.cfg"
    _load(oled, "WIFI", ssid[:16], 10)
    w = network.WLAN(network.STA_IF)
    w.active(True)
    if w.isconnected():
        return True, ""
    try:
        w.connect(ssid, pwd)
    except Exception as err:
        return False, str(err)
    t0 = time.ticks_ms()
    while not w.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > 14000:
            return False, "wifi timeout"
        _load(oled, "WIFI", ssid[:16], min(90, 10 + time.ticks_diff(time.ticks_ms(), t0) // 150))
        time.sleep_ms(200)
        gc.collect()
    return True, ""


def _https_ask(oled, q):
    import socket
    import ssl
    gc.collect()
    path = "/ask?q=" + _enc(q)
    _load(oled, "ASK", "dns", 15)
    infos = socket.getaddrinfo(HOST, PORT)
    ai = infos[0][-1]
    for info in infos:
        if info[0] == 2:
            ai = info[-1]
            break
    del infos
    gc.collect()
    s = socket.socket()
    s.settimeout(14)
    body = b""
    try:
        _load(oled, "ASK", "tcp", 30)
        s.connect(ai)
        gc.collect()
        _load(oled, "ASK", "tls", 45)
        # Prefer TLS1.2 — less RAM than 1.3 on many ESP32 builds
        proto = getattr(ssl, "PROTOCOL_TLS_CLIENT", None) or getattr(ssl, "PROTOCOL_TLS", None)
        if proto is not None:
            ctx = ssl.SSLContext(proto)
            try:
                ctx.verify_mode = ssl.CERT_NONE
            except Exception:
                pass
            opt = 0
            for name in ("OP_NO_TLSv1_3", "OP_NO_TLSv1", "OP_NO_SSLv3"):
                opt |= int(getattr(ssl, name, 0) or 0)
            if opt:
                try:
                    ctx.options |= opt
                except Exception:
                    pass
            s = ctx.wrap_socket(s, server_hostname=HOST)
        else:
            try:
                s = ssl.wrap_socket(s, server_hostname=HOST)
            except TypeError:
                s = ssl.wrap_socket(s)
        gc.collect()
        _load(oled, "ASK", "get", 60)
        req = (
            "GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: Kriky/1\r\n"
            "Accept: text/plain\r\nConnection: close\r\n\r\n"
        ) % (path, HOST)
        s.write(req.encode()) if hasattr(s, "write") else s.send(req.encode())
        del req
        gc.collect()
        acc = bytearray()
        hdr = False
        while len(acc) < LIMIT + 400:
            try:
                chunk = s.read(32) if hasattr(s, "read") else s.recv(32)
            except Exception:
                break
            if not chunk:
                break
            acc.extend(chunk)
            if not hdr:
                i = acc.find(b"\r\n\r\n")
                if i >= 0:
                    acc = bytearray(acc[i + 4:])
                    hdr = True
            if hdr and len(acc) >= LIMIT:
                break
            _load(oled, "ASK", "read", min(95, 60 + len(acc) // 4))
        body = bytes(acc[:LIMIT])
        del acc
    finally:
        try:
            s.close()
        except Exception:
            pass
    gc.collect()
    try:
        return _ascii(body.decode("utf-8"))
    except Exception:
        return _ascii(body.decode("latin-1"))


def clear_pending():
    try:
        import os
        os.remove(ASK_Q)
    except Exception:
        pass


def load_pending():
    try:
        with open(ASK_Q, "r") as f:
            return f.read().strip()
    except Exception:
        return ""


def run(oled, buttons, q):
    """Fetch answer with as much free RAM as possible."""
    clear_pending()
    gc.collect()
    try:
        print("ask free", gc.mem_free())
    except Exception:
        pass
    _load(oled, "ASK", q[:16], 5)
    ok, err = _connect(oled)
    if not ok:
        _show(oled, buttons, "WIFI", err or "wifi fail")
        return
    gc.collect()
    try:
        text = _https_ask(oled, q)
    except Exception as e:
        print("ask", e)
        u = str(e).upper()
        if "MEMORY" in u or "ENOMEM" in u:
            text = "still OOM. use PC server.py http"
        else:
            text = str(e)[:120]
    if not text:
        text = "no answer"
    _load(oled, "ASK", "ok", 100)
    _show(oled, buttons, "ASK", text)
    text = None
    gc.collect()
