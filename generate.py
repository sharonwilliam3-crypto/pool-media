"""Pool Instagram content generator.

Makes, for a given date:
  out/story-YYYY-MM-DD.mp4   12-second 9:16 story video with music (every day)
  out/post-YYYY-MM-DD.jpg    4:5 feed picture (Mondays, Wednesdays, Fridays)
  out/caption-YYYY-MM-DD.txt caption for the feed picture

Usage:
  python generate.py                  # today
  python generate.py --date 2026-11-16
  python generate.py --week           # the next 7 days, to preview or batch-schedule
Needs: Python 3.9+, Pillow, ffmpeg.
"""
import argparse, datetime as dt, json, math, os, shutil, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
FONTS = os.path.join(HERE, "assets", "fonts")
MUSIC = os.path.join(HERE, "assets", "music.m4a")
C = json.load(open(os.path.join(HERE, "content.json"), encoding="utf-8"))

# Pool brand colours (from the app)
BRAND, BRAND2, INK = (43, 58, 143), (59, 77, 179), (20, 26, 51)
GOLD, GOLD_SOFT, WHITE = (232, 155, 0), (252, 239, 208), (255, 255, 255)
SOFT, MUTED, OK = (228, 231, 247), (170, 178, 220), (23, 132, 90)

W, H, FPS, DUR = 1080, 1920, 30, 12.0
POST_DAYS = {0, 2, 4}  # Mon, Wed, Fri


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)

BOLD = lambda s: font("Poppins-Bold.ttf", s)
MED = lambda s: font("Poppins-Medium.ttf", s)
REG = lambda s: font("Inter-Regular.otf", s)
SEMI = lambda s: font("Inter-SemiBold.otf", s)


def rs(n):
    s = f"{n:,.0f}"
    # Indian grouping: 45,000 / 1,20,000
    if n >= 100000:
        a, b = divmod(int(n), 1000)
        s = f"{a // 100},{a % 100:02d},{b:03d}" if a >= 100 else f"{a},{b:03d}"
    return "₹" + s


# ---------- easing / animation helpers ----------
def ease(x):
    x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3

def prog(t, start, dur=0.5):
    return ease((t - start) / dur)

def scene_alpha(t, a, b, fade=0.35):
    """1 inside [a, b], fading in at a and out at b."""
    return min(prog(t, a, fade), 1 - prog(t, b - fade, fade))


def wrap(draw, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=fnt) <= width: cur = test
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


class Layer:
    """Draws onto an RGBA overlay so each element can fade and slide independently."""
    def __init__(self, base): self.base = base
    def text(self, xy, text, fnt, fill, alpha=1.0, dy=0, anchor="la"):
        if alpha <= 0: return
        ov = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).text((xy[0], xy[1] + dy), text, font=fnt, fill=fill + (int(255 * alpha),), anchor=anchor)
        self.base.alpha_composite(ov)
    def box(self, rect, fill, alpha=1.0, r=40, dy=0, outline=None, width=0):
        if alpha <= 0: return
        ov = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
        x0, y0, x1, y1 = rect
        ImageDraw.Draw(ov).rounded_rectangle((x0, y0 + dy, x1, y1 + dy), r, fill=fill + (int(255 * alpha),),
                                             outline=(outline + (int(255 * alpha),)) if outline else None, width=width)
        self.base.alpha_composite(ov)
    def para(self, x, y, text, fnt, fill, width, lh, alpha=1.0, dy=0, anchor="la"):
        d = ImageDraw.Draw(self.base)
        for i, line in enumerate(wrap(d, text, fnt, width)):
            self.text((x, y + i * lh), line, fnt, fill, alpha, dy, anchor)
        return len(wrap(d, text, fnt, width)) * lh


def background(t=0.0, w=W, h=H):
    img = Image.new("RGBA", (w, h), BRAND + (255,))
    d = ImageDraw.Draw(img)
    for i in range(0, h, 4):  # vertical gradient brand -> ink
        k = i / h
        c = tuple(int(BRAND[j] * (1 - k) + INK[j] * k) for j in range(3))
        d.rectangle((0, i, w, i + 4), fill=c + (255,))
    # slow-drifting gold circle for motion
    cx = int(w * 0.85 + 40 * math.sin(t * 0.8)); cy = int(h * 0.12 + 30 * math.cos(t * 0.6))
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(ov).ellipse((cx - 260, cy - 260, cx + 260, cy + 260), fill=BRAND2 + (110,))
    ImageDraw.Draw(ov).ellipse((-200, h - 420, 360, h + 140), fill=BRAND2 + (90,))
    img.alpha_composite(ov)
    return img


def logo(L, x, y, s=1.0, alpha=1.0):
    L.box((x, y, x + int(120 * s), y + int(120 * s)), BRAND2, alpha, r=int(28 * s))
    L.text((x + int(56 * s), y + int(58 * s)), "p", BOLD(int(84 * s)), WHITE, alpha, anchor="mm")
    L.box((x + int(78 * s), y + int(70 * s), x + int(98 * s), y + int(90 * s)), GOLD, alpha, r=int(10 * s))
    L.text((x + int(150 * s), y + int(60 * s)), "Pool", BOLD(int(72 * s)), WHITE, alpha, anchor="lm")


def cta(L, t, start):
    a = prog(t, start, 0.5); dy = int(60 * (1 - a))
    logo(L, 300, 640, 1.3, a)
    L.para(W // 2, 900, "Borrow from verified students at your college", BOLD(64), WHITE, 860, 84, a, dy, anchor="ma")
    b = prog(t, start + 0.5, 0.5)
    L.box((190, 1180, 890, 1300), GOLD, b, r=60, dy=int(40 * (1 - b)))
    L.text((W // 2, 1240), C["site"], BOLD(52), INK, b, int(40 * (1 - b)), anchor="mm")
    c = prog(t, start + 0.9, 0.5)
    L.text((W // 2, 1380), "Link in bio · Free to join", MED(40), SOFT, c, anchor="mm")


# ---------- story templates (each draws one frame at time t) ----------
def story_compare(t, it):
    img = background(t); L = Layer(img)
    a1 = scene_alpha(t, 0, 3.6)
    if a1 > 0:
        L.box((90, 560, 90 + 40 + int(ImageDraw.Draw(img).textlength(it["when"], font=SEMI(44))), 650), GOLD, a1 * prog(t, 0.1), r=45)
        L.text((110, 605), it["when"], SEMI(44), INK, a1 * prog(t, 0.1), anchor="lm")
        p = prog(t, 0.3, 0.6)
        hh = L.para(90, 720, f"Need a {it['name']}?", BOLD(120), WHITE, 900, 150, a1 * p, int(80 * (1 - p)))
        q = prog(t, 1.2, 0.6)
        L.text((90, 720 + hh + 40), "Don't buy it. Borrow it.", MED(64), GOLD_SOFT, a1 * q, int(40 * (1 - q)))
    a2 = scene_alpha(t, 3.6, 8.6)
    if a2 > 0:
        L.text((90, 470), it["name"].upper(), SEMI(42), MUTED, a2 * prog(t, 3.7))
        p = prog(t, 3.8, 0.5)
        L.box((90, 560, 990, 860), (255, 255, 255), a2 * p * 0.12, r=48, dy=int(60 * (1 - p)))
        L.text((150, 620), "Buy it new", MED(48), SOFT, a2 * p, int(60 * (1 - p)))
        L.text((150, 690), rs(it["buy"]), BOLD(120), WHITE, a2 * p, int(60 * (1 - p)))
        s = prog(t, 5.0, 0.4)  # strike-through
        if s > 0:
            tw = ImageDraw.Draw(img).textlength(rs(it["buy"]), font=BOLD(120))
            L.box((140, 762, 140 + int((tw + 20) * s), 776), GOLD, a2, r=7)
        q = prog(t, 4.4, 0.5)
        L.box((90, 900, 990, 1220), GOLD, a2 * q, r=48, dy=int(60 * (1 - q)))
        L.text((150, 960), "Borrow on Pool", MED(48), INK, a2 * q, int(60 * (1 - q)))
        L.text((150, 1030), f"{rs(it['rate'])}/day", BOLD(120), INK, a2 * q, int(60 * (1 - q)))
        r = prog(t, 5.8, 0.5)
        save = it["buy"] - 2 * it["rate"]
        L.box((90, 1290, 990, 1410), (255, 255, 255), a2 * r, r=60)
        L.text((W // 2, 1350), f"Need it for 2 days? You save {rs(save)}", SEMI(44), OK, a2 * r, anchor="mm")
        L.text((90, 1460), "*Approximate prices. Lenders set their own rates.", REG(30), MUTED, a2 * r)
    if t > 8.6: cta(L, t, 8.6)
    return img


def story_tip(t, tip, n):
    img = background(t); L = Layer(img)
    a1 = scene_alpha(t, 0, 8.6)
    if a1 > 0:
        p = prog(t, 0.1)
        L.box((90, 520, 560, 610), GOLD, a1 * p, r=45)
        L.text((325, 565), f"STUDENT TIP #{n}", SEMI(42), INK, a1 * p, anchor="mm")
        q = prog(t, 0.5, 0.7)
        L.para(90, 700, tip, BOLD(96), WHITE, 900, 124, a1 * q, int(80 * (1 - q)))
        r = prog(t, 4.5, 0.6)
        L.box((90, 1460, 300, 1472), GOLD, a1 * r, r=6)
        L.text((90, 1500), "Save this for exam week", MED(44), SOFT, a1 * r)
    if t > 8.6: cta(L, t, 8.6)
    return img


def story_lend(t, it):
    img = background(t); L = Layer(img)
    a1 = scene_alpha(t, 0, 4.2)
    if a1 > 0:
        p = prog(t, 0.2, 0.6)
        L.para(90, 620, f"That {it['name']} you barely use?", BOLD(116), WHITE, 900, 146, a1 * p, int(80 * (1 - p)))
    a2 = scene_alpha(t, 4.2, 8.6)
    if a2 > 0:
        p = prog(t, 4.3, 0.5)
        L.text((90, 600), "Lend it on Pool for", MED(60), SOFT, a2 * p, int(40 * (1 - p)))
        q = prog(t, 4.7, 0.5)
        L.text((90, 690), f"{rs(it['rate'])}/day", BOLD(190), GOLD, a2 * q, int(60 * (1 - q)))
        r = prog(t, 5.6, 0.5)
        for i, line in enumerate(["Only students from your college", "You keep a deposit until it's back", "You choose when and where to meet"]):
            rr = prog(t, 5.6 + i * 0.35, 0.4)
            L.box((90, 960 + i * 130, 130, 1000 + i * 130), GOLD, a2 * rr, r=20)
            L.text((160, 980 + i * 130), line, MED(48), WHITE, a2 * rr, anchor="lm")
    if t > 8.6: cta(L, t, 8.6)
    return img


def story_steps(t):
    img = background(t); L = Layer(img)
    a1 = scene_alpha(t, 0, 8.6)
    if a1 > 0:
        p = prog(t, 0.1)
        L.text((90, 420), "How Pool works", BOLD(104), WHITE, a1 * p, int(50 * (1 - p)))
        for i, (h, s) in enumerate(C["steps"]):
            q = prog(t, 0.9 + i * 1.6, 0.5); y = 640 + i * 330; dy = int(60 * (1 - q))
            L.box((90, y, 990, y + 290), (255, 255, 255), a1 * q * 0.12, r=44, dy=dy)
            L.box((130, y + 40, 230, y + 140), GOLD, a1 * q, r=50, dy=dy)
            L.text((180, y + 90), str(i + 1), BOLD(60), INK, a1 * q, dy, anchor="mm")
            L.text((270, y + 50), h, BOLD(60), WHITE, a1 * q, dy)
            L.para(270, y + 135, s, REG(40), SOFT, 680, 52, a1 * q, dy)
    if t > 8.6: cta(L, t, 8.6)
    return img


def story_for(day):
    """Choose the template + content for a date, deterministically (no state needed)."""
    n = day.toordinal()
    kind = ["compare", "tip", "lend", "compare", "steps", "tip", "lend"][n % 7]
    items, tips = C["items"], C["tips"]
    if kind == "compare": it = items[(n * 5) % len(items)]; return kind, (lambda t: story_compare(t, it))
    if kind == "lend": it = items[(n * 7 + 3) % len(items)]; return kind, (lambda t: story_lend(t, it))
    if kind == "tip": k = (n // 3) % len(tips); return kind, (lambda t: story_tip(t, tips[k], k + 1))
    return kind, story_steps


def render_story(day, path):
    kind, draw = story_for(day)
    tmp = tempfile.mkdtemp()
    try:
        for f in range(int(DUR * FPS)):
            draw(f / FPS).convert("RGB").save(os.path.join(tmp, f"{f:04d}.png"), compress_level=1)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(tmp, "%04d.png")]
        if os.path.exists(MUSIC): cmd += ["-i", MUSIC, "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
        subprocess.run(cmd, check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return kind


# ---------- feed posts (1080 x 1350) ----------
PW, PH = 1080, 1350

def post_for(day):
    n = day.toordinal() // 7 * 3 + [0, None, 1, None, 2][day.weekday()] if day.weekday() in POST_DAYS else None
    if n is None: return None
    kind = ["compare", "tip", "steps", "lend"][n % 4]
    items, tips = C["items"], C["tips"]
    img = background(2.0, PW, PH); L = Layer(img)
    if kind == "compare":
        it = items[(n * 3 + 1) % len(items)]
        L.box((80, 110, 80 + 40 + int(ImageDraw.Draw(img).textlength(it["when"], font=SEMI(38))), 190), GOLD, r=40)
        L.text((100, 150), it["when"], SEMI(38), INK, anchor="lm")
        L.para(80, 240, f"Need a {it['name']}?", BOLD(96), WHITE, 920, 118)
        L.box((80, 560, 1000, 790), (255, 255, 255), 0.12, r=44)
        L.text((130, 600), "Buy it new", MED(40), SOFT)
        L.text((130, 660), rs(it["buy"]), BOLD(96), WHITE)
        tw = ImageDraw.Draw(img).textlength(rs(it["buy"]), font=BOLD(96))
        L.box((120, 717, 140 + int(tw), 729), GOLD, r=6)
        L.box((80, 820, 1000, 1050), GOLD, r=44)
        L.text((130, 860), "Borrow on Pool", MED(40), INK)
        L.text((130, 920), f"{rs(it['rate'])}/day", BOLD(96), INK)
        L.text((80, 1085), "*Approximate prices. Lenders set their own rates.", REG(28), MUTED)
        caption = (f"Need a {it['name']} for a couple of days? Buying new costs about {rs(it['buy'])}. "
                   f"On Pool you can borrow one from a verified student at your college for around {rs(it['rate'])}/day.")
    elif kind == "tip":
        k = (n // 4) % len(tips); tip = tips[k]
        L.box((80, 130, 520, 215), GOLD, r=42)
        L.text((300, 172), f"STUDENT TIP #{k + 1}", SEMI(38), INK, anchor="mm")
        L.para(80, 300, tip, BOLD(84), WHITE, 920, 108)
        caption = f"Student tip #{k + 1}: {tip}"
    elif kind == "steps":
        L.text((80, 110), "How Pool works", BOLD(90), WHITE)
        for i, (h, s) in enumerate(C["steps"]):
            y = 290 + i * 270
            L.box((80, y, 1000, y + 240), (255, 255, 255), 0.12, r=40)
            L.box((120, y + 40, 210, y + 130), GOLD, r=45)
            L.text((165, y + 85), str(i + 1), BOLD(54), INK, anchor="mm")
            L.text((250, y + 40), h, BOLD(54), WHITE)
            L.para(250, y + 115, s, REG(36), SOFT, 700, 46)
        caption = "How Pool works: find it, request it, meet on campus. Every lender and borrower is a verified student from your own college."
    else:
        it = items[(n * 5 + 2) % len(items)]
        L.para(80, 150, f"That {it['name']} you barely use?", BOLD(92), WHITE, 920, 114)
        L.text((80, 560), "Lend it on Pool for", MED(52), SOFT)
        L.text((80, 630), f"{rs(it['rate'])}/day", BOLD(150), GOLD)
        for i, line in enumerate(["Only students from your college", "You keep a deposit until it's back"]):
            L.box((80, 870 + i * 100, 112, 902 + i * 100), GOLD, r=16)
            L.text((140, 886 + i * 100), line, MED(42), WHITE, anchor="lm")
        caption = f"Your {it['name']} could be earning while it sits in your room. List it on Pool and lend it to verified students at your college."
    # footer
    logo(L, 80, 1170, 0.75)
    L.text((1000, 1215), C["site"], SEMI(36), GOLD_SOFT, anchor="rm")
    caption += f"\n\nJoin free: {C['site']} (link in bio)\n\n{C['hashtags']}"
    return kind, img.convert("RGB"), caption


def make(day):
    os.makedirs(OUT, exist_ok=True)
    s = day.isoformat()
    kind = render_story(day, os.path.join(OUT, f"story-{s}.mp4"))
    print(f"{s} story: {kind}")
    p = post_for(day)
    if p:
        k, img, cap = p
        img.save(os.path.join(OUT, f"post-{s}.jpg"), quality=92)
        open(os.path.join(OUT, f"caption-{s}.txt"), "w", encoding="utf-8").write(cap)
        print(f"{s} post: {k}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date"); ap.add_argument("--week", action="store_true")
    a = ap.parse_args()
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    start = dt.date.fromisoformat(a.date) if a.date else dt.datetime.now(ist).date()
    for i in range(7 if a.week else 1):
        make(start + dt.timedelta(days=i))
