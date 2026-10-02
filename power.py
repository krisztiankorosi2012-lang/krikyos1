# Button 1 (IO18): tap = soft reboot, double-tap in 1.5s = shut off.
# While off, one press on IO18 turns the machine back on.
#
# Shut-off keeps USB/Thonny alive (display off + wait). A stuck-low pin
# will not reboot or power down.

from machine import Pin
import machine
import time

PIN = 18
WINDOW_MS = 1500
# Time after the last power tap to decide 1 / 2 taps.
TAP_GAP_MS = 1200


def _pin():
    return Pin(PIN, Pin.IN, Pin.PULL_UP)


def _cx(oled, s, y, c=1):
    oled.text(s, max(0, (128 - len(s) * 8) // 2), y, c)


def wait_high(p, timeout_ms):
    t0 = time.ticks_ms()
    while p.value() == 0:
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            return False
        time.sleep_ms(10)
    time.sleep_ms(30)
    return True


def ignore_wake_hold():
    wait_high(_pin(), 400)


def _draw_reboot_wait(oled, remaining_ms):
    oled.fill(0)
    _cx(oled, "1", 2)
    _cx(oled, "REBOOT", 14)
    _cx(oled, "PRESS 1 AGAIN", 30)
    _cx(oled, "TO SHUT OFF", 40)
    left = max(0, remaining_ms)
    w = int(80 * left / WINDOW_MS) if WINDOW_MS else 0
    oled.rect(24, 54, 80, 8, 1)
    if w > 0:
        oled.fill_rect(24, 54, w, 8, 1)
    oled.show()


def reboot():
    machine.reset()


def _screen_off(oled):
    try:
        oled.poweroff()
        return
    except Exception:
        pass
    try:
        oled.sleep(True)
        return
    except Exception:
        pass
    oled.fill(0)
    oled.show()


def _screen_on(oled):
    try:
        oled.write_cmd(0xAD)
        oled.write_cmd(0x8B)
        oled.write_cmd(0xAF)
    except Exception:
        pass
    try:
        oled.sleep(False)
    except Exception:
        pass


def shutdown(oled):
    oled.fill(0)
    _cx(oled, "OFF", 16)
    _cx(oled, "1 TO TURN ON", 36)
    oled.show()
    time.sleep_ms(400)
    _screen_off(oled)

    p = _pin()
    wait_high(p, 2000)

    try:
        while p.value() == 1:
            time.sleep_ms(20)
    except KeyboardInterrupt:
        _screen_on(oled)
        raise

    time.sleep_ms(50)
    wait_high(p, 2000)
    reboot()


def _count_taps(p):
    """Count power taps after the one that already fired handle_press."""
    taps = 1
    last = p.value()
    t0 = time.ticks_ms()
    last_tap = t0
    while taps < 2:
        now = time.ticks_ms()
        v = p.value()
        # Still holding the first press too long = stuck pin, ignore.
        if taps == 1 and last == 0 and time.ticks_diff(now, t0) > 800:
            print("io18 held, power ignored")
            return 0
        if last == 1 and v == 0:
            time.sleep_ms(12)
            if p.value() == 0:
                taps += 1
                last_tap = time.ticks_ms()
                last = 0
                print("pwr tap", taps)
                continue
        last = v
        if last == 1 and time.ticks_diff(now, last_tap) > TAP_GAP_MS:
            break
        time.sleep_ms(4)
    print("pwr taps", taps)
    return taps


def handle_press(oled, buttons=None):
    """1 tap = reboot after 1.5s. 2 taps = shut off."""
    p = _pin()
    taps = _count_taps(p)
    if taps <= 0:
        return None

    if taps == 2:
        shutdown(oled)
        return "off"

    deadline = time.ticks_add(time.ticks_ms(), WINDOW_MS)
    last = 1
    last_draw = 0
    while True:
        rem = time.ticks_diff(deadline, time.ticks_ms())
        if rem <= 0:
            reboot()
        now = time.ticks_ms()
        if last_draw == 0 or time.ticks_diff(now, last_draw) > 40:
            _draw_reboot_wait(oled, rem)
            last_draw = now
        v = p.value()
        if last == 1 and v == 0:
            time.sleep_ms(20)
            if p.value() == 0:
                shutdown(oled)
                return "off"
        last = v
        time.sleep_ms(8)
