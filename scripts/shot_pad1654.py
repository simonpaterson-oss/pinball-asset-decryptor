"""Shoot the video mode editor mock-ups (PAD-1654) to PNG.

    python scripts/shot_pad1654.py <out dir> [<repo>] [--light]

Opens each docs/plans/video_mode_maker/<screen>.html at 1600x900 in Edge
(Playwright; set PAD_PWLIB to a folder holding the playwright package if it
is not installed) and writes <out>/<screen>.png (and <screen>_light.png with
--light).  Fails on any page error or a font that did not load."""

import os
import sys
import time

SCREENS = ["stage", "phases", "timeline", "play"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    out = os.path.abspath(args[0])
    repo = os.path.abspath(args[1]) if len(args) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    themes = [("", "")] + ([("_light", "#light")] if "--light" in sys.argv else [])
    os.makedirs(out, exist_ok=True)
    if os.environ.get("PAD_PWLIB"):
        sys.path.insert(0, os.environ["PAD_PWLIB"])
    from playwright.sync_api import sync_playwright
    bad = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge" if sys.platform == "win32" else None)
        for screen in SCREENS:
            for suffix, frag in themes:
                page = browser.new_page(viewport={"width": 1600, "height": 900})
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                path = os.path.join(repo, "docs", "plans", "video_mode_maker", screen + ".html")
                page.goto("file:///" + path.replace("\\", "/") + frag)
                page.evaluate("document.fonts.ready")
                time.sleep(0.5)
                fonts = page.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family)")
                if not any("Plex" in f for f in fonts):
                    errors.append("the app's fonts did not load")
                dest = os.path.join(out, screen + suffix + ".png")
                page.screenshot(path=dest)
                print(dest, "errors:", errors or "none", flush=True)
                bad += errors
                page.close()
        browser.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
