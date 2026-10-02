# Kriky Bird — Flappy Bird clone for 128x64 SH1106
# Button 2 (IO19 / D12) and 3 (IO23 / D11) play / flap. Button 1 (IO18 / D13) is power.

import math
import time
from random import randint

W, H = 128, 64
GROUND_Y = 56
BIRD_X = 22
BIRD_W, BIRD_H = 10, 8
PIPE_W = 16
PIPE_GAP = 28
PIPE_SPACING = 96
GRAVITY = 155.0
FLAP_V = -58.0
MAX_V = 110.0
PIPE_SPEED = 58.0
HS_PATH = "kriky_bird.hs"


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


def _text_cx(oled, s, y, c=1):
    oled.text(s, (W - len(s) * 8) // 2, y, c)


def _oval(oled, cx, cy, xr, yr, c, fill=True):
    if xr < 1 or yr < 1:
        oled.pixel(cx, cy, c)
        return
    yr2 = yr * yr
    for dy in range(-yr, yr + 1):
        dx = int(xr * math.sqrt(max(0, yr2 - dy * dy)) / yr)
        if fill:
            oled.hline(cx - dx, cy + dy, dx * 2 + 1, c)
        else:
            oled.pixel(cx - dx, cy + dy, c)
            oled.pixel(cx + dx, cy + dy, c)


def draw_bird(oled, x, y, vel, flap_phase, dead=False):
    x = int(x)
    y = int(y)
    if vel < -22:
        pose = 0
    elif vel > 28:
        pose = 2
    else:
        pose = 1

    oled.fill_rect(x + 2, y + 2, 6, 5, 1)
    oled.fill_rect(x + 3, y + 1, 5, 6, 1)
    oled.fill_rect(x, y + 3, 3, 3, 1)
    oled.pixel(x, y + 2, 1)
    if pose == 0:
        oled.fill_rect(x + 8, y + 2, 3, 2, 1)
        oled.pixel(x + 10, y + 1, 1)
    elif pose == 2:
        oled.fill_rect(x + 8, y + 5, 3, 2, 1)
        oled.pixel(x + 10, y + 6, 1)
    else:
        oled.fill_rect(x + 8, y + 3, 3, 2, 1)
        oled.pixel(x + 11, y + 4, 1)
    oled.pixel(x + 7, y + 3, 0)
    if dead:
        oled.pixel(x + 6, y + 3, 0)
        oled.pixel(x + 8, y + 3, 0)
        oled.pixel(x + 7, y + 2, 0)
        oled.pixel(x + 7, y + 4, 0)
    if dead:
        oled.fill_rect(x + 2, y + 4, 4, 2, 1)
        oled.pixel(x + 1, y + 5, 1)
    elif flap_phase == 0:
        oled.fill_rect(x + 2, y + 0, 4, 2, 1)
        oled.pixel(x + 3, y + 0, 1)
    elif flap_phase == 1:
        oled.fill_rect(x + 2, y + 3, 4, 2, 0)
        oled.hline(x + 2, y + 4, 4, 1)
    else:
        oled.fill_rect(x + 2, y + 6, 4, 2, 1)


def draw_pipe(oled, x, gap_y, gap):
    x = int(x)
    if x >= W or x + PIPE_W < -2:
        return
    top_h = gap_y - gap // 2
    bot_y = gap_y + gap // 2
    x0 = max(0, x)
    x1 = min(W, x + PIPE_W)
    pw = x1 - x0
    if pw <= 0:
        return

    if top_h > 0:
        oled.fill_rect(x0, 0, pw, top_h, 1)
        cap_y = max(0, top_h - 4)
        cap_x = max(0, x - 2)
        cap_w = min(W, x + PIPE_W + 2) - cap_x
        oled.fill_rect(cap_x, cap_y, cap_w, top_h - cap_y, 1)
        if pw > 5 and top_h > 6:
            oled.vline(x0 + 2, 0, max(1, cap_y - 1), 0)

    bh = GROUND_Y - bot_y
    if bh > 0:
        oled.fill_rect(x0, bot_y, pw, bh, 1)
        cap_x = max(0, x - 2)
        cap_w = min(W, x + PIPE_W + 2) - cap_x
        oled.fill_rect(cap_x, bot_y, cap_w, min(4, bh), 1)
        if pw > 5 and bh > 6:
            oled.vline(x0 + 2, bot_y + 5, bh - 5, 0)


def draw_ground(oled, scroll):
    oled.fill_rect(0, GROUND_Y, W, H - GROUND_Y, 1)
    oled.hline(0, GROUND_Y, W, 0)
    s = int(scroll) % 8
    for gx in range(-s, W, 8):
        oled.pixel(gx, GROUND_Y + 2, 0)
        oled.pixel(gx + 3, GROUND_Y + 4, 0)
        oled.pixel(gx + 6, GROUND_Y + 6, 0)


def _gap_y(prev=None):
    lo = PIPE_GAP // 2 + 8
    hi = GROUND_Y - PIPE_GAP // 2 - 6
    y = randint(lo, hi)
    if prev is not None:
        y = max(lo, min(hi, prev + randint(-18, 18)))
        if abs(y - prev) < 8:
            y = prev + (12 if y >= prev else -12)
            y = max(lo, min(hi, y))
    return y


def _collides(by, pipes, gap):
    bx0, by0 = BIRD_X + 1, int(by) + 1
    bx1, by1 = bx0 + BIRD_W - 3, by0 + BIRD_H - 3
    if int(by) < 1 or by1 >= GROUND_Y:
        return True
    for px, gy, _passed in pipes:
        px = int(px)
        if bx1 < px or bx0 > px + PIPE_W:
            continue
        top = gy - gap // 2
        bot = gy + gap // 2
        if by0 < top or by1 > bot:
            return True
    return False


def _new_pipes():
    pipes = []
    x = 150.0
    prev = None
    for _ in range(2):
        gy = _gap_y(prev)
        pipes.append([x, gy, False])
        prev = gy
        x += PIPE_SPACING
    return pipes


def _draw_hud(oled, score):
    label = str(score)
    tw = len(label) * 8
    tx = (W - tw) // 2
    oled.fill_rect(tx - 2, 0, tw + 4, 10, 0)
    oled.text(label, tx, 1, 1)


def _title(oled, buttons, high):
    t0 = time.ticks_ms()
    while True:
        t = time.ticks_diff(time.ticks_ms(), t0) / 1000.0
        oled.fill(0)
        draw_ground(oled, t * 40)
        draw_pipe(oled, 102, 30, 28)
        bob = 28 + int(2.5 * math.sin(t * 4.0))
        draw_bird(oled, 18, bob, math.sin(t * 4.0) * 18, int(t * 10) % 3)
        oled.fill_rect(0, 0, 128, 16, 0)
        _text_cx(oled, "KRIKY BIRD", 3)
        oled.hline(24, 14, 80, 1)
        if int(t * 3) % 2 == 0:
            oled.text("2/3 PLAY", 32, 42, 1)
        oled.text("BEST %d" % high, 4, 55, 1)
        oled.show()

        buttons.update()
        if buttons.play_press():
            return True
        time.sleep_ms(12)


def _game_over(oled, buttons, score, high, new_best):
    medal = None
    if score >= 40:
        medal = "GOLD"
    elif score >= 20:
        medal = "SILVER"
    elif score >= 10:
        medal = "BRONZE"

    t0 = time.ticks_ms()
    while True:
        t = time.ticks_diff(time.ticks_ms(), t0) / 1000.0
        oled.fill(0)
        oled.rect(8, 2, 112, 60, 1)
        oled.fill_rect(10, 4, 108, 11, 1)
        _text_cx(oled, "GAME OVER", 6, 0)
        oled.text("SCORE %d" % score, 24, 20, 1)
        oled.text("BEST  %d" % high, 24, 30, 1)
        if new_best and score > 0 and int(t * 4) % 2 == 0:
            oled.text("NEW BEST", 32, 40, 1)
        elif medal:
            _oval(oled, 18, 44, 4, 4, 1, True)
            oled.text(medal, 26, 41, 1)
        oled.text("2/3 RETRY", 28, 52, 1)
        oled.show()

        buttons.update()
        if buttons.play_press():
            return True
        time.sleep_ms(12)


def _play(oled, buttons):
    bird_y = 28.0
    vel = 0.0
    pipes = _new_pipes()
    score = 0
    alive = True
    started = False
    ground_scroll = 0.0
    gap = PIPE_GAP
    speed = PIPE_SPEED
    flap_n = 0
    last = time.ticks_ms()
    t0 = last

    while True:
        now = time.ticks_ms()
        dt = time.ticks_diff(now, last) / 1000.0
        last = now
        if dt <= 0:
            dt = 0.012
        if dt > 0.05:
            dt = 0.05

        t = time.ticks_diff(now, t0) / 1000.0
        buttons.update()
        flapped = buttons.play_press()
        if flapped:
            if not started:
                started = True
            if alive:
                vel = FLAP_V
                flap_n += 1

        if not started:
            bird_y = 28.0 + 2.0 * math.sin(t * 4.5)
            vel = math.cos(t * 4.5) * 10
        elif started:
            if alive or bird_y + BIRD_H < GROUND_Y:
                vel = min(MAX_V, vel + GRAVITY * dt)
                bird_y += vel * dt
            if bird_y < 0:
                bird_y = 0
                vel = 16
            if alive:
                for p in pipes:
                    p[0] -= speed * dt
                if pipes[0][0] < -PIPE_W - 4:
                    prev = pipes[-1][1]
                    pipes.pop(0)
                    pipes.append([pipes[-1][0] + PIPE_SPACING, _gap_y(prev), False])
                for p in pipes:
                    if (not p[2]) and p[0] + PIPE_W < BIRD_X:
                        p[2] = True
                        score += 1
                        if score % 4 == 0:
                            speed = min(78.0, speed + 3.0)
                            gap = max(22, gap - 1)
                if _collides(bird_y, pipes, gap):
                    alive = False
                    vel = min(vel, 10)
            if bird_y + BIRD_H >= GROUND_Y:
                bird_y = GROUND_Y - BIRD_H
                if not alive:
                    return score, bird_y
                alive = False

        ground_scroll += (speed if started else 30.0) * dt
        phase = (flap_n + int(t * 12)) % 3 if alive else 2

        oled.fill(0)
        for px, gy, _ in pipes:
            draw_pipe(oled, px, gy, gap)
        draw_ground(oled, ground_scroll)
        draw_bird(oled, BIRD_X, bird_y, vel, phase, dead=not alive)
        if not started and int(t * 3) % 2 == 0:
            oled.fill_rect(28, 44, 72, 10, 0)
            oled.text("GET READY", 28, 44, 1)
        _draw_hud(oled, score)
        oled.show()

        elapsed = time.ticks_diff(time.ticks_ms(), now)
        if elapsed < 18:
            time.sleep_ms(18 - elapsed)


def run(oled, buttons):
    high = _load_hs()
    while True:
        if not _title(oled, buttons, high):
            return
        score, _ = _play(oled, buttons)
        new_best = score > high
        if new_best:
            high = score
            _save_hs(high)
        if not _game_over(oled, buttons, score, high, new_best):
            return
