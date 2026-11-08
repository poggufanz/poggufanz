#!/usr/bin/env python3
"""Draw the last year of GitHub contributions as a night sky.

One star per day, brighter on busier days (GitHub's own quartiles). A comet
sweeps the year and every day flares as it passes. The panel is dark, so one
file serves GitHub's light and dark themes.

usage: GITHUB_TOKEN=... python3 sky.py <login> <out.svg>
       python3 sky.py --demo <out.svg>    # synthetic year, no network
"""
import json
import math
import os
import random
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

BG, INK, INK2, INK3 = "#030409", "#f0efea", "#b2b4ba", "#7a7f89"
ACCENT, ACCENT_HI, CREAM, DUSK = "#ffb46e", "#ffd2a1", "#fff1df", "#5a78aa"
FONT = "'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()

# per contribution level 0-4: radius, colour, opacity
STAR = [(1.0, INK, 0.12), (1.7, "#8fa6d6", 0.6), (2.3, "#c6d4ff", 0.78), (3.0, CREAM, 0.92), (3.8, ACCENT_HI, 1.0)]
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
QUERY = ("query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{"
         "totalContributions weeks{contributionDays{date contributionCount contributionLevel weekday}}}}}}")

W, PAD, TOP, RX = 1200, 64, 96, 20
PERIOD, SWEEP = 16.0, 10.0  # seconds: the comet crosses in SWEEP, once every PERIOD


Week = list[tuple[str, int, int, int]]  # (date, count, level 0-4, weekday with Sunday = 0)


def fetch(login: str, token: str) -> tuple[int, list[Week]]:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "contribution-sky"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = json.load(res)
    except urllib.error.HTTPError as e:
        sys.exit(f"GitHub API: HTTP {e.code} {e.reason}")
    user = (body.get("data") or {}).get("user")
    if body.get("errors") or not user:
        sys.exit(f"GitHub API: {body.get('errors') or f'no user {login!r}'}")
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = [[(d["date"], d["contributionCount"], LEVELS[d["contributionLevel"]], d["weekday"])
              for d in w["contributionDays"]] for w in cal["weeks"]]
    return cal["totalContributions"], weeks


def demo() -> tuple[int, list[Week]]:
    """A synthetic year ending today, for previews and the self-check."""
    rnd, end = random.Random(1), date.today()
    d = end - timedelta(days=end.isoweekday() % 7 + 52 * 7)  # the Sunday 52 weeks before this week's
    days = []
    while d <= end:
        n = 0 if rnd.random() < 0.35 else int(rnd.expovariate(1 / 6)) + 1
        days.append((d.isoformat(), n, min(4, (n + 3) // 4), d.isoweekday() % 7))
        d += timedelta(days=1)
    return sum(n for _, n, _, _ in days), [days[i:i + 7] for i in range(0, len(days), 7)]


def spikes(x: float, y: float, s: float) -> str:
    """The six-plus-two diffraction spikes of the header's bright stars, for the busiest day."""
    ray = lambda length, width, angle: (f'<path transform="translate({x:.1f} {y:.1f}) rotate({angle})" '
                                        f'd="M-{length} 0L0 -{width}L{length} 0L0 {width}Z"/>')
    return (f'<g fill="#fff" fill-opacity=".55">{ray(13 * s, 0.7 * s, 90)}{ray(13 * s, 0.7 * s, 30)}'
            f'{ray(13 * s, 0.7 * s, 150)}{ray(6 * s, 0.5 * s, 0)}</g>')


def render(total: int, weeks: list[Week], seed: int = 7) -> str:
    if not weeks:
        sys.exit("empty contribution calendar")
    rnd = random.Random(seed)
    pitch = (W - 2 * PAD) / len(weeks)
    H = round(TOP + 7 * pitch + 34)
    x_s, x_e, y_s, y_e = PAD - 90, W - PAD + 90, TOP + pitch, TOP + 6 * pitch

    sky = [f'<circle cx="{rnd.uniform(8, W - 8):.1f}" cy="{rnd.uniform(8, H - 8):.1f}" r="{0.3 + 0.8 * rnd.random() ** 3:.2f}" '
           f'fill="#fff" fill-opacity="{0.15 + 0.5 * rnd.random():.2f}"/>' for _ in range(110)]

    busiest = max(c for w in weeks for _, c, _, _ in w)
    stars = []
    for i, week in enumerate(weeks):
        x = PAD + (i + 0.5) * pitch
        t = SWEEP * (x - x_s) / (x_e - x_s)  # when the comet's head passes this column
        for _, count, level, wd in week:
            y = TOP + (wd + 0.5) * pitch
            r, color, alpha = STAR[level]
            if level == 0:
                stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" fill-opacity="{alpha}"/>')
                continue
            glow = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{3 * r:.1f}" fill="url(#glow)" opacity="{0.6 * alpha:.2f}"/>' if level >= 3 else ""
            flare = spikes(x, y, 1.0) if count == busiest else ""
            stars.append(f'{glow}{flare}<circle class="f" style="animation-delay:{t:.2f}s" cx="{x:.1f}" cy="{y:.1f}" '
                         f'r="{r}" fill="{color}" fill-opacity="{alpha}"/>')
    assert len(stars) == sum(map(len, weeks)), "a day went missing"

    # month labels where a week starts a new month; drop one whose next label is under 3 weeks away
    starts = [(i, int(w[0][0][5:7])) for i, w in enumerate(weeks) if i == 0 or w[0][0][5:7] != weeks[i - 1][0][0][5:7]]
    starts = [s for k, s in enumerate(starts) if k + 1 == len(starts) or starts[k + 1][0] - s[0] >= 3]
    months = "".join(f'<text x="{PAD + i * pitch:.1f}" y="{TOP - 16}">{MONTHS[m - 1]}</text>' for i, m in starts)
    legend_x = W - PAD - 52
    legend = "".join(f'<circle cx="{legend_x - (4 - lv) * 16}" cy="45" r="{STAR[lv][0]}" fill="{STAR[lv][1]}" '
                     f'fill-opacity="{max(STAR[lv][2], 0.3)}"/>' for lv in range(5))

    angle = math.degrees(math.atan2(y_e - y_s, x_e - x_s))
    comet = (f'<g class="comet"><g transform="rotate({angle:.2f})"><path d="M0 -2.6L-170 -.4V.4L0 2.6Z" fill="url(#tail)"/>'
             f'<path d="M0 0L-120 -9" stroke="#c6d4ff" stroke-opacity=".4" stroke-width=".8"/>'
             f'<circle r="12" fill="url(#head)"/><circle r="2.4" fill="#fff"/></g></g>')

    end = 100 * SWEEP / PERIOD
    at = lambda x, y: f"transform:translate({x}px,{y:.1f}px)"
    css = (f".f{{transform-box:fill-box;transform-origin:center;animation:flare {PERIOD}s linear infinite}}"
           "@keyframes flare{0%,8%,100%{transform:none}1.5%{transform:scale(1.9)}}"
           f".comet{{opacity:0;animation:fly {PERIOD}s linear infinite}}"
           f"@keyframes fly{{0%{{{at(x_s, y_s)};opacity:0}}5%{{opacity:1}}{end - 5:.1f}%{{opacity:1}}"
           f"{end:.1f}%{{{at(x_e, y_e)};opacity:0}}100%{{{at(x_e, y_e)};opacity:0}}}}"
           "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
    defs = (f'<clipPath id="panel"><rect width="{W}" height="{H}" rx="{RX}"/></clipPath>'
            f'<radialGradient id="warm" cx="{W * 0.78:.0f}" cy="0" r="{W * 0.5:.0f}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{ACCENT}" stop-opacity=".08"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="cool" cx="{W * 0.15:.0f}" cy="{H}" r="{W * 0.5:.0f}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{DUSK}" stop-opacity=".14"/><stop offset="1" stop-color="{DUSK}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="glow"><stop offset="0" stop-color="{ACCENT_HI}" stop-opacity=".5"/>'
            f'<stop offset="1" stop-color="{ACCENT_HI}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="head"><stop offset="0" stop-color="#fff"/><stop offset=".25" stop-color="{CREAM}" stop-opacity=".8"/>'
            f'<stop offset=".6" stop-color="{ACCENT}" stop-opacity=".25"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient>'
            f'<linearGradient id="tail" x1="0" x2="-170" y1="0" y2="0" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{CREAM}" stop-opacity=".75"/><stop offset=".3" stop-color="{ACCENT}" stop-opacity=".3"/>'
            f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient>')
    text = (f'<g font-family="{FONT}" font-size="13" fill="{INK3}">{months}'
            f'<text x="{PAD}" y="50" font-size="15" fill="{INK2}"><tspan fill="{ACCENT}">{total:,}</tspan> contributions in the last year</text>'
            f'<text x="{legend_x - 4 * 16 - 12}" y="50" text-anchor="end">quiet</text>'
            f'<text x="{legend_x + 12}" y="50">busy</text></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<style>{css}</style><defs>{defs}</defs><g clip-path="url(#panel)">'
            f'<rect width="{W}" height="{H}" fill="{BG}"/><rect width="{W}" height="{H}" fill="url(#warm)"/>'
            f'<rect width="{W}" height="{H}" fill="url(#cool)"/>{"".join(sky)}{"".join(stars)}{comet}</g>'
            f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="{RX - 0.5}" fill="none" stroke="{INK}" stroke-opacity=".12"/>'
            f'{legend}{text}</svg>\n')


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        sys.exit(__doc__)
    if argv[1] == "--demo":
        total, weeks = demo()
    else:
        token = os.environ.get("GITHUB_TOKEN") or sys.exit("GITHUB_TOKEN is not set")
        total, weeks = fetch(argv[1], token)
    out = Path(argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(total, weeks), encoding="utf-8")
    print(f"{out}: {sum(map(len, weeks))} days, {total} contributions")


if __name__ == "__main__":
    main(sys.argv)
