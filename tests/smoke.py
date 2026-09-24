"""Smoke tests for Hanzi Garden, driven by Playwright against the installed Edge browser.

Setup (once):
  pip install playwright
Run:
  python -m http.server 8765 --bind 127.0.0.1      # from the repo root, in another terminal
  python tests/smoke.py                             # all checks
  python tests/smoke.py migration offline           # selected checks

Screenshots go to tests/out/ (git-ignored).
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("HG_URL", "http://127.0.0.1:8765/")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
WIDE = {"width": 1366, "height": 768}
NARROW = {"width": 390, "height": 844}
LS_KEY = "hanzi-garden-progress-v1"
DAY = 24 * 3600 * 1000

# v1 progress as the old app wrote it: 12 stars, a few characters at different levels.
V1_STATE = {
    "v": 1, "stars": 12, "updatedAt": 1,
    "settings": {"rate": 0.8, "voice": "", "unlockAll": False, "sessionMin": 15},
    "chars": {
        "一": {"l": 5, "d": 9e15, "n": True, "r": 9, "w": 0},
        "二": {"l": 4, "d": 9e15, "n": True, "r": 6, "w": 1},
        "山": {"l": 2, "d": 9e15, "n": True, "r": 3, "w": 0},
        "水": {"l": 0, "d": 0, "n": True, "r": 0, "w": 2},
    },
}


class Page:
    """One browser context + page, with page errors collected and optional preloaded state."""

    def __init__(self, browser, size=WIDE, state=None, session_used=0):
        self.ctx = browser.new_context(viewport=size, service_workers="allow")
        self.errors = []
        init = []
        if state is not None:
            init.append(f"localStorage.setItem({json.dumps(LS_KEY)}, {json.dumps(json.dumps(state))});")
        # Keep the session timer from sending tests to the rest screen unless asked.
        init.append("localStorage.setItem('hanzi-garden-session-v1', JSON.stringify({used: %d, last: Date.now()}));" % session_used)
        # Only seed storage on the very first load, so reloads see what the app saved.
        self.ctx.add_init_script("if (!sessionStorage.getItem('hg-seeded')) { sessionStorage.setItem('hg-seeded', '1'); %s }" % " ".join(init))
        self.p = self.ctx.new_page()
        self.p.on("pageerror", lambda e: self.errors.append(str(e)))

    def open(self, path=""):
        self.p.goto(BASE + path)
        self.p.wait_for_selector(".home-actions")
        return self.p

    def state(self):
        return json.loads(self.p.evaluate(f"localStorage.getItem({json.dumps(LS_KEY)})"))

    def shot(self, name):
        os.makedirs(OUT, exist_ok=True)
        self.p.screenshot(path=os.path.join(OUT, name + ".png"))

    def close(self):
        self.ctx.close()
        assert not self.errors, f"page errors: {self.errors}"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---------- checks ----------

def t_load(browser):
    """Home renders in both sizes; charsets.json is fetched with 200."""
    for name, size in (("wide", WIDE), ("narrow", NARROW)):
        pg = Page(browser, size)
        statuses = []
        pg.p.on("response", lambda r: statuses.append(r.status) if r.url.endswith("data/charsets.json") else None)
        pg.open()
        check(200 in statuses, f"charsets.json not loaded with 200: {statuses}")
        width = pg.p.evaluate("document.documentElement.scrollWidth")
        check(width <= size["width"], f"{name}: horizontal overflow {width}px")
        pg.shot(f"home-{name}")
        pg.close()


def t_migration(browser):
    """v1 progress keeps its stars and character levels after the upgrade."""
    pg = Page(browser, WIDE, state=V1_STATE)
    p = pg.open()
    check(p.inner_text("#starCount").strip().endswith("12"), "stars not shown after migration")
    p.reload()
    p.wait_for_selector(".home-actions")
    s = pg.state()
    check(s["stars"] == 12, "stars lost")
    for c, r in V1_STATE["chars"].items():
        check(s["chars"][c]["l"] == r["l"] and s["chars"][c]["n"], f"level of {c} lost")
    check(s["settings"]["sessionMin"] == 15, "v1 session length changed")
    # Treasure box shows the stored levels as colors.
    p.click(".home-actions .btn.berry")
    p.wait_for_selector(".box-row")
    cls = p.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.box-row .tzg')]
        .map((t) => [t.textContent, t.className]))""")
    check("lv-d" in cls["一"] and "lv-c" in cls["二"] and "lv-b" in cls["山"] and "lv-a" in cls["水"], f"box colors wrong: {cls['一']}, {cls['二']}")
    check("unseen" in cls["三"], "unseen character not dimmed")
    pg.close()


def t_offline(browser):
    """After one online visit the service worker serves the page and charsets.json offline."""
    pg = Page(browser, WIDE)
    p = pg.open()
    p.evaluate("navigator.serviceWorker.ready")
    for _ in range(50):
        if p.evaluate("!!navigator.serviceWorker.controller"):
            break
        p.reload()
        p.wait_for_selector(".home-actions")
        time.sleep(0.1)
    check(p.evaluate("caches.keys().then(async (ks) => { for (const k of ks) { if (await (await caches.open(k)).match('data/charsets.json')) return true; } return false; })"),
          "charsets.json not in the service worker cache")
    pg.ctx.set_offline(True)
    p.reload()
    p.wait_for_selector(".home-actions", timeout=10000)
    pg.ctx.set_offline(False)
    pg.close()


def open_group(p, n):
    """From home, open the n-th (0-based) group card of the current library's map."""
    p.click(".home-actions .btn.leaf")
    p.wait_for_selector(".gcard")
    p.locator(".gcard").nth(n).click()
    p.wait_for_selector(".acts")


def act_labels(p):
    return [t.split()[-1] for t in p.locator(".acts .btn").all_inner_texts()]


def open_act(p, label):
    """Open one activity from the group screen by its button label."""
    p.locator(".acts .btn").nth(act_labels(p).index(label)).click()
    time.sleep(0.4)


def back(p):
    p.locator(".top .btn").first.click()
    time.sleep(0.2)


def t_games_3_4(browser):
    """Every activity of the first 3-4 group opens and takes one answer; daily practice runs."""
    pg = Page(browser, WIDE)
    p = pg.open()
    open_group(p, 0)
    labels = act_labels(p)
    check(len(labels) == 5, f"expected 5 activities, got {labels}")
    for label in labels:
        open_act(p, label)
        if p.locator(".opt").count():
            p.locator(".opt").first.click()
        elif p.locator(".plot").count():
            p.locator(".plot").first.click()
        elif p.locator(".mcard").count():
            check(p.locator(".mcard").count() == 8, "memory round 1 should have 8 cards")
        pg.shot("g34-" + str(labels.index(label)))
        back(p)
        p.wait_for_selector(".acts")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".learn-card, .options")
    pg.close()


CHECKS = {
    "load": t_load,
    "migration": t_migration,
    "offline": t_offline,
    "games34": t_games_3_4,
}


def main(names):
    failed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        for name in names or CHECKS:
            try:
                CHECKS[name](browser)
                print(f"PASS {name}")
            except Exception as e:  # report every check, then fail at the end
                failed += 1
                print(f"FAIL {name}: {e}")
        browser.close()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
