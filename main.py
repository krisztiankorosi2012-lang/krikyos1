# Kriky SUP — Wemos D1 R32 (ESP32 Uno) + SH1106/SSD1306 OLED
#
# OLED -> pins printed SDA and SCL on the D1 R32:
#   VCC -> 3V3
#   GND -> GND
#   SCL -> SCL  (GPIO 22)
#   SDA -> SDA  (GPIO 21)   NOT pin 11 / GPIO 23
#
# Buttons (other side to GND):
#   1  pin 13 / GPIO 18  power (tap reboot, x2 off)
#   2  pin 12 / GPIO 19  play
#   3  pin 11 / GPIO 23  play
# GPIO 21 is SDA — do not put a button on the SDA pin.

try:
    from machine import Pin, SoftI2C
except ImportError:
    from machine import Pin, I2C as SoftI2C
import sys
import time
import gc
import sh1106
import power
# Games / wifi loaded lazily — keeps heap free for WiFi + TLS.

# --- hardware ---
BTN_1 = 18
BTN_2 = 19
BTN_3 = 23
I2C_SCL = 22
I2C_SDA = 21
FLIP_Y = True

I2C_CANDIDATES = (
    (22, 21), (21, 22),
    (22, 23), (23, 22),
    (5, 4), (4, 5),
    (25, 26), (26, 25),
    (32, 33),
    (17, 16),
    (27, 14),
)

_HANDHELD = (
    b"  ##########  ",
    b" ##        ## ",
    b" #  ######  # ",
    b" #  #    #  # ",
    b" #  #    #  # ",
    b" #  ######  # ",
    b" #          # ",
    b" ############ ",
    b" #          # ",
    b" #   o  o   # ",
    b" #          # ",
    b"  ##########  ",
)


class Buttons:
    B1, B2, B3 = 0, 1, 2

    def __init__(self):
        self.oled = None
        self._pwr_ok = False
        self._pins = (
            Pin(BTN_1, Pin.IN, Pin.PULL_UP),
            Pin(BTN_2, Pin.IN, Pin.PULL_UP),
            Pin(BTN_3, Pin.IN, Pin.PULL_UP),
        )
        # Real pin levels so a held/stuck IO18 is not a fake "press" on boot.
        self._last = [p.value() for p in self._pins]
        self.edge = [False, False, False]
        self.held = [False, False, False]
        self._pwr_busy = False

    def update(self):
        for i, pin in enumerate(self._pins):
            v = pin.value()
            self.edge[i] = self._last[i] == 1 and v == 0
            self.held[i] = v == 0
            self._last[i] = v
        if not self._pwr_ok:
            if self._last[0] == 1:
                self._pwr_ok = True
            self.edge[0] = False
            return
        if self.oled is not None and self.edge[0] and not self._pwr_busy:
            self._pwr_busy = True
            try:
                power.handle_press(self.oled, self)
            finally:
                self._pwr_busy = False

    def press(self, i):
        return self.edge[i]

    def play_press(self):
        return self.edge[1] or self.edge[2]

    def any_press(self):
        return self.play_press()


def _hw_or_soft_i2c(scl, sda):
    try:
        from machine import I2C
        for bus in (0, 1):
            try:
                i2c = I2C(bus, scl=Pin(scl), sda=Pin(sda), freq=100000)
                found = i2c.scan()
                print("hw i2c%d scan" % bus, found)
                if found:
                    return i2c
            except Exception as exc:
                print("hw i2c%d" % bus, exc)
    except Exception as exc:
        print("hw i2c", exc)
    return SoftI2C(scl=Pin(scl), sda=Pin(sda), freq=100000)


def _find_i2c():
    reserved = {BTN_1, BTN_2, BTN_3}
    seen = set()
    pairs = ((I2C_SCL, I2C_SDA),) + I2C_CANDIDATES
    for scl, sda in pairs:
        if scl in reserved or sda in reserved or scl == sda:
            continue
        key = (scl, sda)
        if key in seen:
            continue
        seen.add(key)
        try:
            i2c = _hw_or_soft_i2c(scl, sda)
            found = i2c.scan()
        except Exception as exc:
            print("i2c", scl, sda, exc)
            continue
        for addr in (0x3C, 0x3D):
            if addr in found:
                print("oled on scl=%d sda=%d addr=0x%02x" % (scl, sda, addr))
                return i2c, addr
        if found:
            print("i2c devices", found, "on scl=%d sda=%d" % (scl, sda))
    print("oled not found, using scl=%d sda=%d @ 0x3c" % (I2C_SCL, I2C_SDA))
    return _hw_or_soft_i2c(I2C_SCL, I2C_SDA), 0x3C


def _raw_cmds(i2c, addr, cmds):
    payload = bytes(cmds)
    try:
        i2c.writeto(addr, b"\x00" + payload)
        return
    except Exception as exc:
        print("cmd 0x00", exc)
    for cmd in payload:
        try:
            i2c.writeto(addr, bytes((0x80, cmd)))
        except Exception as exc:
            print("cmd 0x80", hex(cmd), exc)


# SSD1306 charge pump 0x8D 0x14 is the usual reason a 0.96" panel stays black.
# SH1106 uses 0xAD 0x8B. Send both so either chip can light.
_INIT_BOTH = (
    0xAE,
    0xD5, 0x80,
    0xA8, 0x3F,
    0xD3, 0x00,
    0x40,
    0x8D, 0x14,
    0xAD, 0x8B,
    0x32,
    0x20, 0x00,
    0xA1,
    0xC8,
    0xDA, 0x12,
    0x81, 0xFF,
    0xD9, 0xF1,
    0xDB, 0x40,
    0xA4,
    0xA6,
    0xAF,
)


def _use_simple_i2c(oled):
    i2c = oled.i2c
    addr = oled.addr

    def write_cmd(cmd):
        i2c.writeto(addr, bytes((0x00, cmd)))

    def write_data(buf):
        i2c.writeto(addr, b"\x40" + buf)

    oled.write_cmd = write_cmd
    oled.write_data = write_data


def wake_panel(oled):
    _raw_cmds(oled.i2c, oled.addr, _INIT_BOTH)
    time.sleep_ms(10)


def init_display():
    i2c, addr = _find_i2c()
    _raw_cmds(i2c, addr, _INIT_BOTH)

    oled = None
    try:
        import ssd1306
        oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=addr)
        print("driver: ssd1306")
    except Exception as exc:
        print("ssd1306 n/a", exc)

    if oled is None:
        oled = sh1106.SH1106_I2C(128, 64, i2c, addr=addr, rotate=0)
        _use_simple_i2c(oled)
        print("driver: sh1106")

    wake_panel(oled)
    print("panel woke")
    oled.fill(0)
    oled.show()
    return oled


def blit_icon(oled, x, y, rows, color=1):
    for j, row in enumerate(rows):
        py = y + j
        if py < 0 or py > 63:
            continue
        for i, ch in enumerate(row):
            if ch in (35, 111):  # '#' or 'o'
                px = x + i
                if 0 <= px <= 127:
                    oled.fill_rect(px, py, 1, 1, color)


def text_cx(oled, s, y, color=1):
    oled.text(s, (128 - len(s) * 8) // 2, y, color)


def wait_ms(oled, buttons, ms):
    end = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        buttons.update()
        if buttons.play_press():
            return True
        time.sleep_ms(10)
    return False


def boot_screen(oled, buttons):
    """Quick logo + 1/2/3 help, then menu."""
    icon_w = len(_HANDHELD[0])
    x = (128 - icon_w) // 2

    oled.fill(0)
    blit_icon(oled, x, 2, _HANDHELD)
    oled.show()
    if wait_ms(oled, buttons, 80):
        return

    oled.fill(0)
    text_cx(oled, "KRIKY OS", 0)
    text_cx(oled, "1, 2, 3", 10)
    oled.text("1 REBOOT", 4, 22)
    oled.text("  x2 OFF 1=ON", 4, 30)
    oled.text("2 PLAY", 4, 40)
    oled.text("3 PLAY", 4, 48)
    bar_x, bar_y, bar_w, bar_h = 24, 58, 80, 6
    oled.rect(bar_x, bar_y, bar_w, bar_h, 1)
    oled.show()
    if wait_ms(oled, buttons, 40):
        return

    for n in range(1, bar_w - 3, 4):
        oled.fill_rect(bar_x + 2, bar_y + 2, n, bar_h - 4, 1)
        oled.show()
        buttons.update()
        if buttons.play_press():
            return
        time.sleep_ms(4)

    oled.fill_rect(bar_x + 2, bar_y + 2, bar_w - 4, bar_h - 4, 1)
    oled.show()
    wait_ms(oled, buttons, 60)


def draw_menu(oled, index, names):
    oled.fill(0)
    oled.rect(0, 0, 128, 64, 1)
    oled.fill_rect(0, 0, 128, 10, 1)
    text_cx(oled, "KRIKY SUP", 1, 0)

    y = 13
    for i, name in enumerate(names):
        selected = i == index
        if selected:
            oled.fill_rect(4, y - 1, 120, 10, 1)
            oled.text(">", 6, y, 0)
            oled.text(name, 16, y, 0)
        else:
            oled.text(name, 16, y, 1)
        y += 10

    oled.hline(4, 54, 120, 1)
    oled.text("2 PLAY 3 NEXT", 12, 56, 1)
    oled.show()


def _run_browser(oled, buttons):
    gc.collect()
    import wifi
    try:
        wifi.browse(oled, buttons)
    finally:
        gc.collect()


def _run_game(name, oled, buttons):
    gc.collect()
    mod = __import__(name)
    try:
        mod.run(oled, buttons)
    finally:
        gc.collect()


def menu_loop(oled, buttons):
    games = (
        ("KRIKY BIRD", "kriky_bird"),
        ("KRIKY HOP", "kriky_hop"),
        ("KRIKY DASH", "kriky_dash"),
        ("BROWSER", None),
    )
    names = tuple(g[0] for g in games)
    index = 0
    draw_menu(oled, index, names)

    while True:
        buttons.update()
        if buttons.press(Buttons.B3):
            index = (index + 1) % len(games)
            draw_menu(oled, index, names)
        if buttons.press(Buttons.B2):
            mod = games[index][1]
            if mod is None:
                _run_browser(oled, buttons)
            else:
                _run_game(mod, oled, buttons)
            draw_menu(oled, index, names)
        time.sleep_ms(12)


def _show_error(oled, err):
    print("crash:", err)
    try:
        sys.print_exception(err)
    except Exception:
        pass
    if oled is None:
        return
    try:
        oled.fill(0)
        oled.text("ERROR", 0, 0)
        msg = str(err)
        y = 12
        while msg and y < 56:
            oled.text(msg[:16], 0, y)
            msg = msg[16:]
            y += 10
        oled.show()
    except Exception:
        pass


def _pending_ask(oled, buttons):
    """If ask.q exists, fetch with max free RAM (no games loaded)."""
    import ask_fetch
    q = ask_fetch.load_pending()
    if not q:
        return False
    print("pending ask", q)
    try:
        ask_fetch.run(oled, buttons, q)
    except Exception as err:
        _show_error(oled, err)
        try:
            ask_fetch.clear_pending()
        except Exception:
            pass
    gc.collect()
    return True


def main():
    oled = None
    try:
        print("kriky boot")
        oled = init_display()
        print("display ok")
        buttons = Buttons()
        buttons.oled = oled
        gc.collect()
        try:
            print("free", gc.mem_free())
        except Exception:
            pass
        # Cloud ASK uses a reboot so TLS has enough heap.
        if _pending_ask(oled, buttons):
            pass
        else:
            print("boot screen")
            boot_screen(oled, buttons)
        print("menu")
        menu_loop(oled, buttons)
    except KeyboardInterrupt:
        print("stopped - hit Run on main.py")
        if oled is not None:
            try:
                oled.fill(0)
                oled.text("STOPPED", 36, 28)
                oled.show()
            except Exception:
                pass
    except Exception as err:
        _show_error(oled, err)
        raise


if __name__ == "__main__":
    main()
