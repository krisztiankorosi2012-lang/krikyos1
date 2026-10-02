# WiFi setup + question UI for ESP32. ASK reboots into ask_fetch (saves RAM).
# Default API: https://krikymachine.vercel.app/

import time
import gc

CFG = "wifi.cfg"
ASK_Q = "ask.q"
AP_SSID = "KRIKY-SETUP"
AP_PASS = "kriky123"
_SETS = (
    ("Chars", "abcdefghijklmnopqrstuvwxyz "),
    ("CHARS", "ABCDEFGHIJKLMNOPQRSTUVWXYZ "),
    ("numbers", "1234567890.-_!@#*?"),
)


def _cx(oled, s, y, c=1):
    oled.text(s, max(0, (128 - len(s) * 8) // 2), y, c)


def _wlan():
    import network
    gc.collect()
    try:
        network.WLAN(network.AP_IF).active(False)
    except Exception:
        pass
    w = network.WLAN(network.STA_IF)
    w.active(True)
    return w


def load_cfg():
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


def save_cfg(ssid, pwd):
    with open(CFG, "w") as f:
        f.write(ssid + "\n" + pwd + "\n")


def is_up():
    try:
        return _wlan().isconnected()
    except Exception:
        return False


def ip_addr():
    try:
        return _wlan().ifconfig()[0]
    except Exception:
        return "?"


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


def _pick_list(oled, buttons, title, names):
    index = 0
    n = len(names)
    vis = 5
    while True:
        start = 0
        if n > vis:
            start = max(0, min(index - 2, n - vis))
        oled.fill(0)
        oled.fill_rect(0, 0, 128, 11, 1)
        _cx(oled, title, 2, 0)
        y = 13
        for i, name in enumerate(names[start:start + vis]):
            real = start + i
            if real == index:
                oled.fill_rect(2, y - 1, 124, 10, 1)
                oled.text(">", 4, y, 0)
                oled.text(name[:14], 14, y, 0)
            else:
                oled.text(name[:14], 14, y, 1)
            y += 10
        oled.show()
        buttons.update()
        if buttons.press(0):
            return n - 1
        if buttons.press(1):
            return index
        if buttons.press(2):
            index = (index + 1) % n
        time.sleep_ms(12)


def _show_lines(oled, buttons, title, text):
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
        oled.text("2 OK  3 MORE", 8, 55)
        oled.show()
        buttons.update()
        if buttons.press(1) or buttons.press(0):
            return
        if buttons.press(2):
            top = 0 if top + 4 >= len(lines) else top + 1
        time.sleep_ms(12)


def _draw_keys(oled, keys, idx, y0):
    n = len(keys)
    per = 10 if keys.startswith("1234567890") else (len(keys) if len(keys) <= 8 else 8)
    rows = (n + per - 1) // per
    row = idx // per if idx < n else rows - 1
    vis = 2 if per >= 10 else 3
    start = 0
    if rows > vis:
        start = min(max(0, row), rows - vis)
    for r in range(vis):
        rr = start + r
        if rr >= rows:
            break
        y = y0 + r * 10
        j0 = rr * per
        count = min(per, n - j0)
        stride = 12 if count >= 10 else 16
        x0 = max(0, (128 - count * stride) // 2)
        for c in range(count):
            j = j0 + c
            ch = "_" if keys[j] == " " else keys[j]
            x = x0 + c * stride
            if j == idx:
                oled.fill_rect(x - 1, y - 1, 10, 10, 1)
                oled.text(ch, x, y, 0)
            else:
                oled.text(ch, x, y, 1)


def _type_text(oled, buttons, title, start="", done="GO"):
    buf = start
    page = 0
    set_i = 0
    idx = 0
    save_ms = 0
    h2 = 0
    h2ms = 0
    h2del = False
    h3ms = 0
    last = time.ticks_ms()
    while True:
        now = time.ticks_ms()
        dt = time.ticks_diff(now, last)
        last = now
        keys = _SETS[set_i][1] if set_i < len(_SETS) else ""
        n = len(keys)
        slots = n + 1
        oled.fill(0)
        oled.fill_rect(0, 0, 128, 11, 1)
        if page == 0:
            head = buf[-16:] if buf else title[:16]
        else:
            head = _SETS[set_i][0]
        _cx(oled, head, 2, 0)
        shown = buf[-15:] if len(buf) > 15 else buf
        if page == 0:
            y = 13
            labels = [p[0] for p in _SETS] + [done, "BACK"]
            for i, name in enumerate(labels):
                if i == set_i:
                    oled.fill_rect(2, y - 1, 124, 10, 1)
                    oled.text(">", 4, y, 0)
                    oled.text(name, 14, y, 0)
                else:
                    oled.text(name, 14, y, 1)
                y += 10
        else:
            oled.text(shown + "_", 0, 13)
            _draw_keys(oled, keys, idx, 26)
            oled.text("2 ADD 3 NEXT", 0, 56)
            if idx >= n:
                oled.fill_rect(103, 55, 25, 10, 1)
                oled.text("SET", 104, 56, 0)
            else:
                oled.text("SET", 104, 56)
        oled.show()
        buttons.update()
        if buttons.held[1] and buttons.held[2]:
            save_ms += dt
            h2 = 0
            h3ms = 0
            if save_ms > 450:
                return buf
            time.sleep_ms(12)
            continue
        save_ms = 0
        if page == 0:
            n_set = len(_SETS) + 2
            if buttons.press(2):
                set_i = (set_i + 1) % n_set
            if buttons.press(1):
                if set_i == len(_SETS):
                    return buf
                if set_i > len(_SETS):
                    return None
                page = 1
                idx = 0
            if buttons.press(0):
                if buf:
                    buf = buf[:-1]
                else:
                    return None
        else:
            if buttons.press(2):
                idx = (idx + 1) % slots
                h3ms = 0
            if buttons.held[2] and not buttons.held[1]:
                h3ms += dt
                if h3ms > 380:
                    idx = (idx + 1) % slots
                    h3ms = 240
            else:
                if not buttons.held[2]:
                    h3ms = 0
            if buttons.press(1):
                h2 = 1
                h2ms = 0
                h2del = False
            if h2 and buttons.held[1] and not buttons.held[2]:
                h2ms += dt
                lim = 420 if not h2del else 150
                if h2ms > lim:
                    if buf:
                        buf = buf[:-1]
                    h2del = True
                    h2ms = 0
            elif h2 and not buttons.held[1]:
                if not h2del:
                    if idx >= n:
                        page = 0
                    else:
                        buf += keys[idx]
                h2 = 0
            if buttons.press(0):
                if buf:
                    buf = buf[:-1]
                else:
                    page = 0
        time.sleep_ms(12)


def _do_connect(oled, buttons, ssid, pwd, timeout_ms=14000):
    _load(oled, "CONNECTING", ssid[:16], 8)
    gc.collect()
    try:
        w = _wlan()
        if w.isconnected():
            try:
                w.disconnect()
            except Exception:
                pass
            time.sleep_ms(150)
            gc.collect()
        w.connect(ssid, pwd)
        t0 = time.ticks_ms()
        while not w.isconnected():
            gone = time.ticks_diff(time.ticks_ms(), t0)
            if gone > timeout_ms:
                _show_lines(oled, buttons, "WIFI", "timeout. check pass")
                return False
            _load(oled, "CONNECTING", ssid[:16], min(95, 8 + gone * 87 // timeout_ms))
            time.sleep_ms(200)
            gc.collect()
        _load(oled, "CONNECTING", "ok", 100)
        save_cfg(ssid, pwd)
        _show_lines(oled, buttons, "WIFI", "ok " + ip_addr())
        return True
    except Exception as err:
        msg = str(err)
        if "MEMORY" in msg.upper() or "ENOMEM" in msg.upper():
            msg = "out of memory. reboot then JOIN"
        _show_lines(oled, buttons, "WIFI", msg)
        return False


def _scan(oled, buttons):
    _load(oled, "SCANNING", "wifi", 20)
    gc.collect()
    try:
        w = _wlan()
        _load(oled, "SCANNING", "wifi", 45)
        nets = w.scan()
        _load(oled, "SCANNING", "wifi", 100)
    except Exception as err:
        msg = str(err)
        if "MEMORY" in msg.upper() or "ENOMEM" in msg.upper():
            msg = "scan OOM. reboot then SCAN"
        _show_lines(oled, buttons, "SCAN", msg)
        return False
    items = []
    seen = set()
    for row in nets:
        ssid = row[0]
        try:
            ssid = ssid.decode()
        except Exception:
            ssid = str(ssid)
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        rssi = row[3] if len(row) > 3 else 0
        auth = row[4] if len(row) > 4 else 0
        items.append((ssid, rssi, auth))
        if len(items) >= 8:
            break
    del nets
    gc.collect()
    if not items:
        _show_lines(oled, buttons, "SCAN", "no networks")
        return False
    names = []
    for ssid, rssi, auth in items:
        lock = "*" if auth else " "
        names.append("%s%s%d" % (lock, ssid[:10], rssi))
    names.append("BACK")
    i = _pick_list(oled, buttons, "SCAN", names)
    if i >= len(items):
        return False
    ssid, rssi, auth = items[i]
    pwd = ""
    if auth:
        pwd = _type_text(oled, buttons, "PASSWORD", done="JOIN")
        if pwd is None:
            return False
    return _do_connect(oled, buttons, ssid, pwd)


def _connect_saved(oled, buttons):
    ssid, pwd = load_cfg()
    if not ssid:
        _show_lines(oled, buttons, "WIFI", "no wifi.cfg yet")
        return False
    return _do_connect(oled, buttons, ssid, pwd)


def _need_net(oled, buttons):
    gc.collect()
    if is_up():
        return True
    ssid, pwd = load_cfg()
    names = ("SCAN", "SETUP", "BACK")
    if ssid:
        names = ("JOIN", "SCAN", "SETUP", "BACK")
    while True:
        gc.collect()
        i = _pick_list(oled, buttons, "WIFI", names)
        if names[i] == "JOIN":
            if _connect_saved(oled, buttons):
                return True
        elif names[i] == "SCAN":
            if _scan(oled, buttons):
                return True
        elif names[i] == "SETUP":
            gc.collect()
            import wifi_ap
            if wifi_ap.run(oled, buttons):
                return True
        else:
            return False


def _try_math(q):
    s = q.strip().replace(" ", "")
    if len(s) < 3:
        return ""
    ok = "0123456789+-*/().%"
    for c in s:
        if c not in ok:
            return ""
    if s.strip("0123456789") == "":
        return ""
    try:
        v = eval(s)
    except Exception:
        return ""
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return str(v)


def _queue_ask(oled, q):
    """Save question and soft-reboot so ask_fetch runs with free heap."""
    with open(ASK_Q, "w") as f:
        f.write(q.strip()[:80])
    _load(oled, "ASK", "rebooting", 100)
    time.sleep_ms(400)
    import machine
    machine.reset()


def browse(oled, buttons):
    gc.collect()
    try:
        print("browser free", gc.mem_free())
    except Exception:
        pass
    if not load_cfg()[0]:
        if not _need_net(oled, buttons):
            return
    else:
        if not is_up():
            if not _need_net(oled, buttons):
                return
    while True:
        gc.collect()
        q = _type_text(oled, buttons, "ASK", done="GO")
        if not q:
            return
        q = q.strip()
        if not q:
            continue
        math = _try_math(q)
        if math:
            _show_lines(oled, buttons, "ASK", math)
            continue
        _show_lines(
            oled, buttons, "ASK",
            "will reboot then fetch from cloud. 2 OK",
        )
        _queue_ask(oled, q)
