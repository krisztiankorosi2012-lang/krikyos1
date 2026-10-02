# Kriky Dash — side-scrolling runner for 128x64 OLED
# 2/3 = jump. Dodge ground spikes and floating blocks.

import time
from random import randint

W, H = 128, 64
GROUND = 54
PW, PH = 8, 8
GRAVITY = 400.0
JUMP_V = -118.0
SPEED0 = 128.0
SPEED_MAX = 230.0
HS_PATH = "kriky_dash.hs"


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


def _draw_player(oled, x, y, dead=False):
    x, y = int(x), int(y)
    oled.fill_rect(x + 1, y + 1, 6, 6, 1)
    oled.pixel(x + 3, y + 3, 0)
    oled.pixel(x + 5, y + 3, 0)
    if dead:
        oled.pixel(x + 4, y + 5, 0)
    oled.pixel(x, y + 7, 1)
    oled.pixel(x + 7, y + 7, 1)


def _draw_obs(oled, o):
    kind, x, y, w, h = o
    x, y = int(x), int(y)
    if x > W or x + w < 0:
        return
    if kind == 0:
        # spike
        mid = x + w // 2
        oled.fill_rect(x, GROUND - 2, w, 2, 1)
        oled.vline(mid, y, GROUND - y, 1)
        oled.pixel(mid - 1, y + 2, 1)
        oled.pixel(mid + 1, y + 2, 1)
    else:
        oled.fill_rect(x, y, w, h, 1)
        if w > 4 and h > 4:
            oled.rect(x + 1, y + 1, w - 2, h - 2, 0)


def _spawn(x, score):
    if randint(0, 1) == 0:
        # ground spike
        return [0, float(x), GROUND - 10, 10, 10]
    # floating block
    top = randint(18, 34)
    return [1, float(x), float(top), 12, 10]


def _title(oled, buttons, high):
    t0 = time.ticks_ms()
    while True:
        t = time.ticks_diff(time.ticks_ms(), t0) / 1000.0
        oled.fill(0)
        _cx(oled, "KRIKY DASH", 4)
        oled.hline(16, 14, 96, 1)
        oled.fill_rect(0, GROUND, W, H - GROUND, 1)
        bob = GROUND - PH + (0 if int(t * 5) % 2 else -6)
        _draw_player(oled, 24, bob)
        _draw_obs(oled, [0, 90, GROUND - 10, 10, 10])
        if int(t * 3) % 2 == 0:
            oled.text("2/3 JUMP", 32, 22, 1)
        oled.text("BEST %d" % high, 4, 34, 1)
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


def _hit(px, py, obs):
    bx0, by0 = px + 1, py + 1
    bx1, by1 = px + PW - 2, py + PH - 1
    kind, ox, oy, ow, oh = obs
    ox, oy = int(ox), int(oy)
    if kind == 0:
        # triangle-ish: treat as thin rect near tip + base
        if bx1 < ox or bx0 > ox + ow:
            return False
        if by1 < oy + 2:
            return False
        return by1 >= oy + 2
    return not (bx1 < ox or bx0 > ox + ow or by1 < oy or by0 > oy + oh)


def _play(oled, buttons):
    px = 22.0
    py = float(GROUND - PH)
    vy = 0.0
    on_ground = True
    speed = SPEED0
    dist = 0.0
    score = 0
    obs = []
    last = time.ticks_ms()
    scroll = 0.0

    while True:
        now = time.ticks_ms()
        dt = time.ticks_diff(now, last) / 1000.0
        last = now
        if dt <= 0:
            dt = 0.012
        if dt > 0.05:
            dt = 0.05

        buttons.update()
        if on_ground and (
            buttons.play_press()
            or (dist > 16 and (buttons.held[1] or buttons.held[2]))
        ):
            vy = JUMP_V
            on_ground = False

        vy = min(240.0, vy + GRAVITY * dt)
        py += vy * dt
        if py >= GROUND - PH:
            py = GROUND - PH
            vy = 0.0
            on_ground = True

        dist += speed * dt
        scroll += speed * dt
        score = int(dist // 10)
        speed = min(SPEED_MAX, SPEED0 + score * 1.2)

        for o in obs:
            o[1] -= speed * dt
        while obs and obs[0][1] + obs[0][3] < -4:
            obs.pop(0)

        gap_lo = max(38, 58 - score // 6)
        gap_hi = max(gap_lo + 10, 82 - score // 4)
        if not obs:
            obs.append(_spawn(float(W + 8), score))
        elif obs[-1][1] < W - 42:
            obs.append(_spawn(obs[-1][1] + randint(gap_lo, gap_hi), score))

        for o in obs:
            if _hit(px, py, o):
                return score

        oled.fill(0)
        # ground
        oled.fill_rect(0, GROUND, W, H - GROUND, 1)
        s = int(scroll) % 10
        for gx in range(-s, W, 10):
            oled.pixel(gx, GROUND + 3, 0)
        for o in obs:
            _draw_obs(oled, o)
        _draw_player(oled, px, py)
        oled.fill_rect(0, 0, 48, 10, 0)
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
