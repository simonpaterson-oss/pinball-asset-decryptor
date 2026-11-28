"""Original placeholder art for the video mode maker's worked example, Night Harbour (PAD-1658).

    python scripts/vm_demo_art.py <mode folder> [--sources <folder>]

Draws every picture docs/plans/video_mode_maker.md's example names (a sea and a skyline to tile, a boat, a
drone, a mine, a bolt, a crate, a warship, a sight, a shell) into <mode folder>/art at the sizes its document
gives, and copies the example document in as video_mode.json. With --sources it also writes files to bring in
by each import kind: an animated GIF, a numbered PNG run, a sprite sheet with gutters, a grid sheet and a
green-screen video (needs ffmpeg). All shapes are drawn here; PAD ships no game content.
"""
import json
import math
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
EXAMPLE = os.path.join(REPO, "pinball_decryptor", "core", "video_mode", "examples", "night_harbour.json")


def _grad(w, h, top, bottom):
    img = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    return img


def sea():
    w, h = 1360, 468
    img = _grad(w, h, (10, 34, 64), (3, 10, 22))
    d = ImageDraw.Draw(img)
    for row in range(14):
        y = 18 + row * 32
        amp = 3 + row * 0.6
        pts = [(x, y + amp * math.sin((x / w) * 2 * math.pi * 8 + row)) for x in range(0, w + 1, 8)]
        d.line(pts, fill=(60, 120 + row * 6, 170, 160), width=2)
    return img


def skyline():
    w, h = 1360, 300
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x, k = 0, 0
    while x < w:
        bw = 40 + (k * 37) % 70
        bh = 80 + (k * 53) % 180
        d.rectangle([x, h - bh, x + bw, h], fill=(18, 24, 40, 255))
        for wy in range(h - bh + 10, h - 8, 18):
            for wx in range(x + 6, x + bw - 6, 14):
                if (wx * 7 + wy * 3 + k) % 5 == 0:
                    d.rectangle([wx, wy, wx + 5, wy + 8], fill=(232, 190, 90, 255))
        x += bw + 4
        k += 1
    return img


def boat_frames():
    out = []
    for f in range(4):
        img = Image.new("RGBA", (192, 128), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.polygon([(20, 70), (176, 70), (150, 100), (40, 100)], fill=(214, 222, 230, 255))
        d.rectangle([70, 44, 130, 70], fill=(70, 90, 120, 255))
        d.rectangle([84, 30, 100, 44], fill=(232, 163, 61, 255))
        for i in range(5):
            r = 6 + ((f + i) % 4) * 3
            d.ellipse([20 - i * 4 - r, 96 - r // 2, 20 - i * 4 + r, 96 + r // 2], fill=(220, 240, 255, 140))
        out.append(img)
    return out


def drone_frames():
    out = []
    for f in range(2):
        img = Image.new("RGBA", (96, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([28, 24, 68, 44], fill=(200, 70, 70, 255))
        span = 40 if f == 0 else 28
        d.line([(48 - span, 22), (48 + span, 22)], fill=(230, 230, 230, 255), width=3)
        d.ellipse([44, 30, 52, 38], fill=(255, 230, 120, 255))
        out.append(img)
    return out


def blob(size, fill, spikes=0):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w, h = size
    d.ellipse([w * 0.15, h * 0.15, w * 0.85, h * 0.85], fill=fill)
    for i in range(spikes):
        a = 2 * math.pi * i / spikes
        d.line([(w / 2, h / 2), (w / 2 + math.cos(a) * w * 0.48, h / 2 + math.sin(a) * h * 0.48)], fill=fill, width=4)
    return img


def warship():
    img = Image.new("RGBA", (640, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(10, 140), (630, 140), (580, 210), (60, 210)], fill=(90, 100, 112, 255))
    d.rectangle([200, 80, 440, 140], fill=(120, 130, 142, 255))
    d.rectangle([280, 30, 340, 80], fill=(140, 150, 160, 255))
    for x in (230, 380):
        d.ellipse([x - 18, 96, x + 18, 132], fill=(240, 110, 95, 255))
    return img


def sight():
    img = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 88, 88], outline=(127, 176, 230, 255), width=4)
    d.line([(48, 0), (48, 96)], fill=(127, 176, 230, 255), width=2)
    d.line([(0, 48), (96, 48)], fill=(127, 176, 230, 255), width=2)
    return img


def sheet(frames):
    fw, fh = frames[0].size
    s = Image.new("RGBA", (fw * len(frames), fh), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        s.paste(f, (i * fw, 0))
    return s


def burst_frames(n=16, size=128):
    out = []
    for i in range(n):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        t = (i + 1) / n
        r = int(size * 0.45 * t)
        c = size // 2
        d.ellipse([c - r, c - r, c + r, c + r], fill=(255, int(220 - 160 * t), 60, int(255 * (1 - t * 0.7))))
        rr = int(r * 0.55)
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=(255, 250, 200, int(255 * (1 - t))))
        out.append(img)
    return out


def make_mode(mode_dir):
    art = os.path.join(mode_dir, "art")
    os.makedirs(art, exist_ok=True)
    sea().save(os.path.join(art, "sea.png"))
    skyline().save(os.path.join(art, "skyline.png"))
    sheet(boat_frames()).save(os.path.join(art, "boat.png"))
    sheet(drone_frames()).save(os.path.join(art, "drone.png"))
    blob((64, 64), (150, 150, 160, 255), 8).save(os.path.join(art, "mine.png"))
    Image.new("RGBA", (24, 8), (255, 240, 120, 255)).save(os.path.join(art, "bolt.png"))
    blob((56, 56), (180, 130, 70, 255)).save(os.path.join(art, "crate.png"))
    warship().save(os.path.join(art, "warship.png"))
    sight().save(os.path.join(art, "sight.png"))
    blob((32, 32), (240, 110, 95, 255)).save(os.path.join(art, "shell.png"))
    shutil.copy2(EXAMPLE, os.path.join(mode_dir, "video_mode.json"))


def make_sources(folder, ffmpeg=None):
    """Files to bring in, one per import kind; returns {kind: path}."""
    os.makedirs(folder, exist_ok=True)
    out = {}
    frames = burst_frames()
    gif = os.path.join(folder, "burst.gif")
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
    out["gif"] = gif
    run = os.path.join(folder, "run")
    os.makedirs(run, exist_ok=True)
    for i, f in enumerate(frames):
        f.save(os.path.join(run, "spark_%04d.png" % (i + 1)))
    out["numbered"] = os.path.join(run, "spark_0001.png")
    grid = Image.new("RGBA", (4 * 128, 4 * 128), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        grid.paste(f, ((i % 4) * 128, (i // 4) * 128))
    out["grid"] = os.path.join(folder, "burst_grid.png")
    grid.save(out["grid"])
    gut = Image.new("RGBA", (5 * 60 + 4 * 14, 2 * 44 + 18), (0, 0, 0, 0))
    for i, f in enumerate(drone_frames() * 5):
        gut.paste(f.crop((16, 10, 80, 54)), ((i % 5) * 74, (i // 5) * 62))
    out["auto"] = os.path.join(folder, "drones_sheet.png")
    gut.save(out["auto"])
    out["picture"] = os.path.join(folder, "buoy.png")
    blob((80, 120), (232, 163, 61, 255)).save(out["picture"])
    ff = ffmpeg or shutil.which("ffmpeg")
    if ff:
        tmp = os.path.join(folder, "_vid")
        os.makedirs(tmp, exist_ok=True)
        for i in range(36):
            img = Image.new("RGB", (320, 180), (0, 255, 0))
            d = ImageDraw.Draw(img)
            x = 40 + i * 6
            d.ellipse([x, 60, x + 60, 120], fill=(230, 80, 60))
            d.rectangle([x + 20, 40, x + 40, 60], fill=(250, 250, 250))
            img.save(os.path.join(tmp, "%03d.png" % i))
        out["video"] = os.path.join(folder, "greenscreen.mp4")
        subprocess.run([ff, "-v", "error", "-y", "-framerate", "24", "-i", os.path.join(tmp, "%03d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", out["video"]], check=True)
        shutil.rmtree(tmp, ignore_errors=True)
    return out


if __name__ == "__main__":
    make_mode(os.path.abspath(sys.argv[1]))
    if "--sources" in sys.argv:
        print(json.dumps(make_sources(os.path.abspath(sys.argv[sys.argv.index("--sources") + 1]))))
