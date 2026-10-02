# Phone AP WiFi setup — imported only when needed (saves RAM).

import time
import gc

AP_SSID = "KRIKY-SETUP"
AP_PASS = "kriky123"
CFG = "wifi.cfg"

_FORM = b"""HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n<!doctype html>
<title>Kriky</title>
<meta name=viewport content=width=device-width>
<h3>Kriky WiFi</h3>
<form action=/save>
SSID<br><input name=s autofocus><br>
Password<br><input name=p type=password><br>
<input type=submit value=Connect>
</form>
"""

_SAVED = b"""HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n<!doctype html>
<title>Kriky</title>
<h3>Saved</h3>
<p>Connecting. You can close this.</p>
"""


def _cx(oled, s, y, c=1):
    oled.text(s, max(0, (128 - len(s) * 8) // 2), y, c)


def _urldecode(s):
    out = []
    i = 0
    s = s.replace("+", " ")
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                out.append(chr(int(s[i + 1:i + 3], 16)))
                i += 3
                continue
            except Exception:
                pass
        out.append(s[i])
        i += 1
    return "".join(out)


def _qs(q):
    data = {}
    if not q:
        return data
    for part in q.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            data[_urldecode(k)] = _urldecode(v)
    return data


def run(oled, buttons):
    import network
    import socket
    import wifi

    gc.collect()
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    try:
        ap.config(essid=AP_SSID, password=AP_PASS, authmode=network.AUTH_WPA_WPA2_PSK)
    except Exception:
        ap.config(essid=AP_SSID)
    time.sleep_ms(200)
    ip = "192.168.4.1"
    try:
        ip = ap.ifconfig()[0]
    except Exception:
        pass

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 80))
    srv.listen(1)
    srv.settimeout(0.25)

    got = None
    while got is None:
        oled.fill(0)
        _cx(oled, "SETUP WIFI", 0)
        oled.text("JOIN " + AP_SSID, 0, 14)
        oled.text("PASS " + AP_PASS, 0, 26)
        oled.text("OPEN " + ip, 0, 38)
        oled.text("2/3 CANCEL", 24, 54)
        oled.show()
        buttons.update()
        if buttons.play_press() or buttons.press(0):
            try:
                srv.close()
            except Exception:
                pass
            ap.active(False)
            return False
        try:
            cl, addr = srv.accept()
        except Exception:
            continue
        try:
            cl.settimeout(3)
            req = b""
            while b"\r\n\r\n" not in req and len(req) < 600:
                chunk = cl.recv(64)
                if not chunk:
                    break
                req += chunk
            line = req.split(b"\r\n", 1)[0].decode()
            path = line.split(" ")[1] if " " in line else "/"
            if path.startswith("/save"):
                q = path.split("?", 1)[1] if "?" in path else ""
                data = _qs(q)
                ssid = data.get("s") or ""
                pwd = data.get("p") or ""
                cl.send(_SAVED)
                cl.close()
                if ssid:
                    got = (ssid, pwd)
                    break
            else:
                cl.send(_FORM)
            cl.close()
        except Exception:
            try:
                cl.close()
            except Exception:
                pass

    try:
        srv.close()
    except Exception:
        pass
    ap.active(False)
    gc.collect()
    if got:
        wifi.save_cfg(got[0], got[1])
        return wifi._do_connect(oled, buttons, got[0], got[1])
    return False
