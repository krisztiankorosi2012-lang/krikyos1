# Kriky Hop — vertical platform hopper for 128x64 OLED
# 2 = jump / left lean while held with 3 for right; 2/3 both play on title.
# Simple: 2 = left, 3 = right, auto-bounce on platforms.

import time
from random import randint

W, H = 128, 64
PW, PH = 18, 3
BW, BH = 8, 8
GRAVITY = 220.0
JUMP_V = -78.0
MOVE = 78.0
HS_PATH = "kriky_hop.hs"


def _load_hs():
    try:
        with open(HS_PATH, "r") as f:
            return int(f.read().strip() or "0")
    except Exception:
        return 0


def _save_hs(score):
    try:
        with open(HS_PATH, "w") as f:
            f.write(str(int(score)))
    except Exception:
        pass


def _cx(oled, s, y, c=1):
    oled.text(s, (W - len(s) * 8) // 2, y, c)


def _draw_hopper(oled, x, y, dead=False):
    x, y = int(x), int(y)
    oled.fill_rect(x + 1, y + 2, 6, 5, 1)
    oled.fill_rect(x + 2, y, 4, 3, 1)
    oled.pixel(x + 3, y + 2, 0)
    oled.pixel(x + 5, y + 2, 0)
    if dead:
        oled.pixel(x + 3, y + 3, 0)
        oled.pixel(x + 5, y + 3, 0)
    oled.pixel(x + 1, y + 7, 1)
    oled.pixel(x + 6, y + 7, 1)


def _draw_plat(oled, x, y, w=PW):
    x, y = int(x), int(y)
    if y < 0 or y >= H:
        return
    oled.fill_rect(x, y, w, PH, 1)
    oled.hline(x, y, w, 0)


def _new_plats():
    plats = []
    y = 52.0
    x = 50.0
    for i in range(7):
        if i == 0:
            x = 48.0
            w = 32
        else:
            x = float(randint(4, W - PW - 4))
            w = PW
        plats.append([x, y, w])
        y -= 11.0
    return plats


def _title(oled, buttons, high):
    t0 = time.ticks_ms()
    while True:
        t = time.ticks_diff(time.ticks_ms(), t0) / 1000.0
        oled.fill(0)
        _cx(oled, "KRIKY HOP", 4)
        oled.hline(20, 14, 88, 1)
        bob = 36 + int(2 * (1 if int(t * 6) % 2 else -1))
        _draw_plat(oled, 48, 48, 32)
        _draw_hopper(oled, 60, bob)
        if int(t * 3) % 2 == 0:
            oled.text("2/3 PLAY", 32, 20, 1)
        oled.text("2 L  3 R", 28, 55, 1)
        oled.text("BEST %d" % high, 4, 28, 1)
        oled.show()
        buttons.update()
        if buttons.play_press():
            return True
        time.sleep_ms(12)


def _game_over(oled, buttons, score, high, new_best):
    while True:
        oled.fill(0)
        oled.rect(8, 8, 112, 48, 1)
        _cx(oled, "GAME OVER", 14)
        oled.text("SCORE %d" % score, 28, 28, 1)
        oled.text("BEST  %d" % high, 28, 38, 1)
        if new_best and score > 0:
            oled.text("NEW BEST", 32, 48, 1)
        else:
            oled.text("2/3 RETRY", 28, 48, 1)
        oled.show()
        buttons.update()
        if buttons.play_press():
            return True
        time.sleep_ms(12)


def _play(oled, buttons):
    plats = _new_plats()
    x = 56.0
    y = 40.0
    vx = 0.0
    vy = JUMP_V
    score = 0
    cam = 0.0
    last = time.ticks_ms()
    alive = True

    while True:
        now = time.ticks_ms()
        dt = time.ticks_diff(now, last) / 1000.0
        last = now
        if dt <= 0:
            dt = 0.012
        if dt > 0.05:
            dt = 0.05

        buttons.update()
        left = buttons.held[1]
        right = buttons.held[2]
        if left and not right:
            vx = -MOVE
        elif right and not left:
            vx = MOVE
        else:
            vx *= 0.82

        if alive:
            vy = min(140.0, vy + GRAVITY * dt)
            x += vx * dt
            y += vy * dt
            if x < 0:
                x = 0
                vx = 0
            if x > W - BW:
                x = W - BW
                vx = 0

            if vy > 0:
                foot = y + BH
                for p in plats:
                    px, py, pw = p[0], p[1], p[2]
                    if foot >= py and foot <= py + PH + 3 and y + BH - vy * dt <= py + 1:
                        if x + BW > px and x < px + pw:
                            y = py - BH
                            vy = JUMP_V
                            break

            # camera follows upward progress
            screen_y = y - cam
            if screen_y < 22:
                lift = 22 - screen_y
                cam -= lift
                score = max(score, int(-cam // 8))

            # recycle platforms below camera
            for p in plats:
                if p[1] - cam > H + 4:
                    highest = min(pl[1] for pl in plats)
                    p[1] = highest - randint(9, 13)
                    p[0] = float(randint(2, W - PW - 2))
                    p[2] = PW if randint(0, 4) else 24

            if y - cam > H + 8:
                alive = False
                return score

        oled.fill(0)
        for px, py, pw in plats:
            sy = int(py - cam)
            if -4 < sy < H:
                _draw_plat(oled, px, sy, pw)
        _draw_hopper(oled, x, y - cam, dead=not alive)
        oled.fill_rect(0, 0, 40, 10, 0)
        oled.text(str(score), 2, 1, 1)
        oled.show()

        elapsed = time.ticks_diff(time.ticks_ms(), now)
        if elapsed < 16:
            time.sleep_ms(16 - elapsed)


def run(oled, buttons):
    high = _load_hs()
    while True:
        if not _title(oled, buttons, high):
            return
        score = _play(oled, buttons)
        new_best = score > high
        if new_best:
            high = score
            _save_hs(high)
        if not _game_over(oled, buttons, score, high, new_best):
            return
