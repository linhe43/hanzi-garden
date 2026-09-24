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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = "\u25cb"  # blank mark on listening cards

# All Chinese text comes from the app's own data: UI strings from index.html, characters from charsets.json.
with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
    _html = f.read()
_a = _html.index('id="content">') + len('id="content">')
UI = json.loads(_html[_a:_html.index("</script>", _a)])["ui"]
with open(os.path.join(ROOT, "data", "charsets.json"), encoding="utf-8") as f:
    DATA = json.load(f)
LIBS = DATA["libraries"]


def char(li, gi, k):
    """Character record k of group gi in library li."""
    return LIBS[li]["groups"][gi]["chars"][k]


def fmt(tpl, **kw):
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl


# v1 characters used below: the first three of group 1 and two of group 2 in the 3-4 library (the v1 set).
C1, C2, C3 = (char(0, 0, k)["c"] for k in range(3))
C_MOUNTAIN, C_WATER = char(0, 1, 2)["c"], char(0, 1, 3)["c"]

# v1 progress as the old app wrote it: 12 stars, a few characters at different levels.
V1_STATE = {
    "v": 1, "stars": 12, "updatedAt": 1,
    "settings": {"rate": 0.8, "voice": "", "unlockAll": False, "sessionMin": 15},
    "chars": {
        C1: {"l": 5, "d": 9e15, "n": True, "r": 9, "w": 0},
        C2: {"l": 4, "d": 9e15, "n": True, "r": 6, "w": 1},
        C_MOUNTAIN: {"l": 2, "d": 9e15, "n": True, "r": 3, "w": 0},
        C_WATER: {"l": 0, "d": 0, "n": True, "r": 0, "w": 2},
    },
}


class Page:
    """One browser context + page, with page errors collected and optional preloaded state."""

    def __init__(self, browser, size=WIDE, state=None, session_used=0, **ctx):
        self.ctx = browser.new_context(viewport=size, service_workers="allow", **ctx)
        self.errors = []
        init = []
        if state is not None:
            init.append(f"localStorage.setItem({json.dumps(LS_KEY)}, {json.dumps(json.dumps(state))});")
        # Keep the session timer from sending tests to the rest screen unless asked.
        init.append("localStorage.setItem('hanzi-garden-session-v1', JSON.stringify({used: %d, last: Date.now()}));" % session_used)
        # Only seed storage on the very first load, so reloads see what the app saved.
        self.ctx.add_init_script("if (!sessionStorage.getItem('hg-seeded')) { sessionStorage.setItem('hg-seeded', '1'); %s }" % " ".join(init))
        # Record what the app says instead of speaking it.
        self.ctx.add_init_script("""window.__said = [];
          if (window.speechSynthesis) speechSynthesis.speak = (u) => { if (u.text.trim()) window.__said.push(u.text); };""")
        self.p = self.ctx.new_page()
        self.p.on("pageerror", lambda e: self.errors.append(str(e)))

    def open(self, path=""):
        self.p.goto(BASE + path)
        self.p.wait_for_selector(".home-actions")
        return self.p

    def said(self):
        return self.p.evaluate("window.__said.splice(0)")

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


def kai_loaded(p):
    p.evaluate("document.fonts.ready")
    return p.evaluate("""() => [...document.fonts].some((f) => f.family.replace(/"/g, '') === 'HG Kai' && f.status === 'loaded')""")


def t_font(browser):
    """Characters use the bundled Kai font on every device; the file is fetched once."""
    pg = Page(browser, NARROW)
    hits = []
    pg.p.on("response", lambda r: hits.append(r.status) if r.url.endswith("fonts/kai.woff2") else None)
    p = pg.open()
    check(kai_loaded(p), "HG Kai not loaded")
    fam = p.eval_on_selector(".title-tiles .han", "(e) => getComputedStyle(e).fontFamily")
    check(fam.startswith('"HG Kai"'), f"title tiles not using HG Kai: {fam}")
    check(hits == [200], f"kai.woff2 fetched {hits}")
    pg.shot("font-home-narrow")
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
    check("lv-d" in cls[C1] and "lv-c" in cls[C2] and "lv-b" in cls[C_MOUNTAIN] and "lv-a" in cls[C_WATER], f"box colors wrong: {cls[C1]}, {cls[C2]}")
    check("unseen" in cls[C3], "unseen character not dimmed")
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
    check(p.evaluate("caches.keys()") == ["hanzi-garden-v5"], f"cache names: {p.evaluate('caches.keys()')}")
    check(p.evaluate("caches.open('hanzi-garden-v5').then((c) => c.match('data/charsets.json')).then((r) => !!r)"),
          "charsets.json not in the service worker cache")
    check(p.evaluate("caches.open('hanzi-garden-v5').then((c) => c.match('fonts/kai.woff2')).then((r) => !!r)"),
          "kai.woff2 not in the service worker cache")
    pg.ctx.set_offline(True)
    p.reload()
    p.wait_for_selector(".home-actions", timeout=10000)
    check(kai_loaded(p), "Kai font not available offline")
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


def charsets():
    return DATA


def open_settings(p):
    """Parent settings need a 2-second hold; Shift+Enter is the keyboard equivalent."""
    p.focus(".home-foot .parent")
    p.keyboard.press("Shift+Enter")
    p.wait_for_selector(".panel")


def settings_select(p, label_key):
    return f".panel label:has-text('{UI[label_key]}') select"


def pick_library(p, lib_id):
    """Pick a library: the panel stays open with the library defaults filled in, then confirm closes it."""
    open_settings(p)
    p.click(f'.lib-card[data-lib="{lib_id}"]')
    time.sleep(0.2)
    check(p.locator(".panel").count() == 1, "settings closed right after picking a library")
    prof = next(l for l in LIBS if l["id"] == lib_id)["profile"]
    check(p.input_value(settings_select(p, "dailyNew")) == str(prof["dailyNew"]), "daily new default not filled in")
    check(p.input_value(settings_select(p, "sessionLen")) == str(prof["sessionMin"]), "session default not filled in")
    check(p.is_checked(".panel label.inline input >> nth=0") == prof["showPinyin"], "pinyin default not filled in")
    p.click(f".panel .btn.leaf:has-text('{UI['confirm']}')")
    p.wait_for_selector(".panel", state="detached")
    p.wait_for_selector(".home-actions")


GAME_LABEL = {k: UI[k] for k in ("learn", "listen", "picture", "memory", "flowers", "fill")}
BUILT_GAMES = {"learn", "listen", "picture", "memory", "flowers", "fill"}


def t_libraries(browser):
    """Switching libraries changes the home tag, map, group activities and the library defaults."""
    data = charsets()
    pg = Page(browser, NARROW)
    p = pg.open()
    for lib in data["libraries"]:
        pick_library(p, lib["id"])
        size = sum(len(g["chars"]) for g in lib["groups"])
        tag = p.inner_text(".lib-tag")
        check(lib["name"] in tag and f"/{size}" in tag, f"home tag wrong: {tag}")
        open_settings(p)
        check(p.get_attribute(f'.lib-card[data-lib="{lib["id"]}"]', "aria-checked") == "true", "selected card not marked")
        session = p.eval_on_selector_all(".panel select", "(ss) => ss.map((s) => s.value)")
        check(str(lib["profile"]["sessionMin"]) in session, f"session length not applied: {session}")
        check(p.is_checked(".panel label.inline input") == lib["profile"]["showPinyin"], "pinyin default not applied")
        pg.shot(f"settings-{lib['id']}")
        p.click(".panel .btn.leaf")
        p.click(".home-actions .btn.leaf")
        p.wait_for_selector(".gcard")
        check(p.inner_text(".stage-h") == lib["name"], "map title is not the library name")
        check(p.locator(".gcard").count() == len(lib["groups"]), "map lists other libraries' groups")
        check(p.inner_text(".gcard .num") == fmt(UI["levelN"], n=1), "level numbers do not restart per library")
        locked = p.eval_on_selector_all(".gcard", "(cs) => cs.map((c) => c.classList.contains('locked'))")
        check(not locked[0] and all(locked[1:]), f"unlock state wrong for a fresh library: {locked[:3]}")
        pg.shot(f"map-{lib['id']}")
        p.locator(".gcard").first.click()
        p.wait_for_selector(".acts")
        g0 = lib["groups"][0]
        expect = [GAME_LABEL[x] for x in lib["profile"]["games"] if x in BUILT_GAMES and
                  (x != "picture" or sum(1 for c in g0["chars"] if c["pic"]) >= 4)]
        check(act_labels(p) == expect, f"{lib['id']} activities {act_labels(p)} != {expect}")
        p.goto(BASE)
        p.wait_for_selector(".home-actions")
    # Library defaults can still be changed by hand afterwards.
    open_settings(p)
    session_sel = settings_select(p, "sessionLen")
    p.select_option(session_sel, "30")
    p.click(".panel label.inline input >> nth=0")
    p.click(".panel .btn.leaf")
    open_settings(p)
    check(p.input_value(session_sel) == "30", "manual session length lost")
    check(p.is_checked(".panel label.inline input >> nth=0") is False, "manual pinyin toggle lost")  # 6-7 default is on
    pg.close()


def t_unlock(browser):
    """Unlocking is counted per library: passing 3-4 group 1 does not open 4-5 group 2."""
    data = charsets()
    g1 = data["libraries"][0]["groups"][0]["chars"]
    st = json.loads(json.dumps(V1_STATE))
    st["chars"] = {x["c"]: {"l": 1, "d": 9e15, "n": True, "r": 1, "w": 0} for x in g1[:8]}
    pg = Page(browser, WIDE, state=st)
    p = pg.open()
    p.click(".home-actions .btn.leaf")
    p.wait_for_selector(".gcard")
    locked = p.eval_on_selector_all(".gcard", "(cs) => cs.map((c) => c.classList.contains('locked'))")
    check(locked[:3] == [False, False, True], f"3-4 unlock wrong: {locked[:3]}")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    pick_library(p, "age-4-5")
    p.click(".home-actions .btn.leaf")
    p.wait_for_selector(".gcard")
    locked = p.eval_on_selector_all(".gcard", "(cs) => cs.map((c) => c.classList.contains('locked'))")
    check(locked[:2] == [False, True], f"4-5 unlock wrong: {locked[:2]}")
    pg.close()


def seeded(lib_id, chars, new_today=0):
    """A v2 state on library lib_id with the given per-character records and new characters already taken today."""
    return {"v": 2, "stars": 0, "updatedAt": 1, "chars": chars,
            "settings": {"rate": 0.8, "voice": "", "unlockAll": False, "sessionMin": 15, "libraryId": lib_id, "showPinyin": False},
            "newLog": {"day": time.strftime("%Y-%m-%d"), "byLib": {lib_id: new_today}}}


def profile(li):
    return LIBS[li]["profile"]


def learn_chars(p):
    """Characters shown on the learn cards, stepping through with 'next'."""
    seen = []
    while True:
        seen.append(p.inner_text(".learn-box .han"))
        nxt = p.locator(".learn-nav .btn").last
        if UI["done"] in nxt.inner_text():
            return seen
        nxt.click()


def t_daily(browser):
    data = charsets()
    lib34, lib45 = data["libraries"][0], data["libraries"][1]
    # 1) 3-4 library: the first run introduces dailyNew characters in order, the second run none.
    n34 = profile(0)["dailyNew"]
    pg = Page(browser, WIDE)
    p = pg.open()
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".learn-card")
    check(learn_chars(p) == [char(0, 0, k)["c"] for k in range(n34)], "first daily run should teach dailyNew characters")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    p.click(".home-actions .btn.sun")
    time.sleep(0.5)
    check(p.locator(".learn-card").count() == 0, "second daily run on the same day introduced new characters")
    check(pg.state()["newLog"]["byLib"]["age-3-4"] == n34, "newLog not counted")
    pg.close()

    # 2) Review is global: on 4-5 with today's new allowance used up, a due 3-4 character is still reviewed.
    pg = Page(browser, WIDE, state=seeded("age-4-5", {C_WATER: {"l": 2, "d": 0, "n": True, "r": 2, "w": 0}}, new_today=10))
    p = pg.open()
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".options")
    opts = p.eval_on_selector_all(".opt", "(os) => os.map((o) => o.getAttribute('aria-label'))")
    check(C_WATER in opts and p.locator(".learn-card").count() == 0, f"due 3-4 character not reviewed on 4-5: {opts}")
    pg.close()

    # 3) Finished library: new characters come from the next library; the home note shows once.
    done = {x["c"]: {"l": 3, "d": 9e15, "n": True, "r": 3, "w": 0} for g in lib34["groups"] for x in g["chars"]}
    pg = Page(browser, NARROW, state=seeded("age-3-4", done))
    p = pg.open()
    check(p.locator(".lib-done").count() == 1, "library-finished note missing")
    pg.shot("home-lib-done")
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".learn-card")
    check(learn_chars(p) == [char(1, 0, k)["c"] for k in range(n34)], "new characters not taken from the next library")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    check(p.locator(".lib-done").count() == 0, "library-finished note shown twice")
    pg.close()


def t_nopic(browser):
    """Characters without pictures: big word on the learn card, listening cards in memory, no picture quiz."""
    data = charsets()
    lib56 = data["libraries"][2]
    g0 = [x["c"] for x in lib56["groups"][0]["chars"]]
    pg = Page(browser, NARROW)
    p = pg.open()
    pick_library(p, "age-5-6")
    open_group(p, 0)
    check(UI["picture"] not in act_labels(p), "picture quiz shown for a group without pictures")
    open_act(p, UI["learn"])
    check(p.locator(".learn-word").count() == 1 and p.locator(".learn-pic").count() == 0, "learn card should show the big word")
    check(p.locator(".learn-info .word").count() == 1, "word shown twice on the learn card")
    pg.shot("learn-56")
    back(p)
    open_act(p, UI["memory"])
    says = p.eval_on_selector_all(".mcard .say", "(ss) => ss.map((s) => s.textContent)")
    hans = p.eval_on_selector_all(".mcard .front .han", "(ss) => ss.map((s) => s.textContent)")
    check(len(says) == 4 and len(hans) == 4, f"round 1 should have 4 listening + 4 character cards: {says} {hans}")
    for c in hans:
        check(any(MARK in s and c not in s for s in says), f"listening card leaks the character {c}: {says}")
    pg.shot("memory-56")
    back(p)
    open_act(p, UI["listen"])
    opts = p.eval_on_selector_all(".opt", "(os) => os.map((o) => o.getAttribute('aria-label'))")
    check(len(set(opts)) == 4, f"listen quiz needs 4 options: {opts}")
    pg.close()

    # 4-5 group with 5 pictures: picture quiz only asks the pictured characters and only offers pictured options.
    lib45 = data["libraries"][1]
    gi = next(i for i, g in enumerate(lib45["groups"]) if sum(1 for x in g["chars"] if x["pic"]) == 5)
    pics = {x["c"] for g in lib45["groups"] for x in g["chars"] if x["pic"]} | {x["c"] for x in data["libraries"][0]["groups"][0]["chars"]}
    pg = Page(browser, WIDE, state=seeded("age-4-5", {}))
    p = pg.open()
    open_settings(p)
    p.click(".panel label.inline >> nth=1")  # unlock all groups
    p.click(".panel .btn.leaf")
    open_group(p, gi)
    open_act(p, UI["picture"])
    rounds = 0
    while p.locator(".prompt .big-pic").count():
        rounds += 1
        check(p.inner_text(".prompt .big-pic").strip() != "", "empty picture prompt")
        opts = p.eval_on_selector_all(".opt", "(os) => os.map((o) => o.getAttribute('aria-label'))")
        check(all(o in pics for o in opts), f"option without a picture: {opts}")
        # Answer by trying each option until the round advances.
        for i in range(4):
            if p.locator(".opt.right").count():
                break
            b = p.locator(".opt").nth(i)
            if not b.is_disabled():
                b.click()
        time.sleep(1.9)
    check(rounds >= 5, f"picture quiz asked {rounds} rounds")
    pg.close()


def t_fill(browser):
    """Fill-in-the-word: blank shows in the word, no second valid option, right answer fills the blank."""
    data = charsets()
    lib56 = data["libraries"][2]
    words = {x["w"] for l in data["libraries"] for g in l["groups"] for x in g["chars"]}
    group = lib56["groups"][0]["chars"]
    pg = Page(browser, WIDE)
    p = pg.open()
    pick_library(p, "age-5-6")
    open_group(p, 0)
    open_act(p, UI["fill"])
    for _ in range(len(group)):
        p.wait_for_selector(".fill-word")
        shown = p.eval_on_selector(".fill-word", "(w) => [...w.children].map((k) => k.classList.contains('tzg') ? '_' : k.textContent).join('')")
        opts = p.eval_on_selector_all(".opt", "(os) => os.map((o) => o.getAttribute('aria-label'))")
        # Two words can blank to the same display (X+A, X+B both show X_); the answer is the one offered.
        answer = next(x for x in group if x["w"].replace(x["c"], "_") == shown and x["c"] in opts)
        c = answer["c"]
        check(c in opts and len(set(opts)) == 4, f"options {opts} for {shown}")
        for o in opts:
            if o != c:
                check(answer["w"].replace(c, o) not in words, f"{o} also fills {shown}")
        p.click(f'.opt[aria-label="{c}"]')
        check(p.eval_on_selector_all(".fill-word .tzg.filled", "(ts) => ts.map((t) => t.textContent)") == [c] * answer["w"].count(c),
              "blank not filled with the answer")
        pg.shot("fill-56")
        time.sleep(1.9)
    p.wait_for_selector(".end")
    pg.close()


def t_speech(browser):
    """Speech template follows the character's own library; the pinyin toggle controls the learn card."""
    # On 5-6, reviewing a 3-4 character (wordOf) still uses the wordOf phrasing; a 5-6 character uses charWord.
    old, new = char(0, 1, 5), char(2, 0, 2)
    pg = Page(browser, WIDE, state=seeded("age-5-6", {old["c"]: {"l": 2, "d": 0, "n": True, "r": 2, "w": 0}}, new_today=10))
    p = pg.open()
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".options")
    time.sleep(0.6)
    p.click(f'.opt[aria-label="{old["c"]}"]')
    time.sleep(0.3)
    said = pg.said()
    check(fmt(UI["sayCharWordOf"], c=old["c"], w=old["w"]) in said, f"wordOf template not used for {old['c']}: {said}")
    check(all(new["w"] not in t for t in said), "wrong character spoken")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    open_group(p, 0)
    pg.said()
    p.click(f'.char-row .tzg:has-text("{new["c"]}")')
    time.sleep(0.3)
    check(fmt(UI["sayCharCharWord"], c=new["c"], w=new["w"]) in pg.said(), f"charWord template not used for {new['c']}")
    open_act(p, UI["listen"])
    time.sleep(0.6)
    lead = UI["promptCharWord"].split("{")[0]
    check(any(t.startswith(lead) for t in pg.said()), "charWord prompt template not used")
    pg.close()

    # Pinyin: off by default on 3-4, on after the toggle.
    pg = Page(browser, WIDE)
    p = pg.open()
    open_group(p, 0)
    open_act(p, UI["learn"])
    check(p.locator(".learn-card .pinyin").count() == 0, "pinyin shown while the toggle is off")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    open_settings(p)
    p.click(".panel label.inline input >> nth=0")
    p.click(".panel .btn.leaf")
    open_group(p, 0)
    open_act(p, UI["learn"])
    check(p.locator(".learn-card .pinyin").count() == 1, "pinyin hidden while the toggle is on")
    pg.close()


def t_box(browser):
    """Treasure box: total line, one tab per library opening on the current one, long press shows pinyin."""
    rec = {"l": 3, "d": 9e15, "n": True, "r": 3, "w": 0}
    chars = {c: dict(rec) for c in [C1, C2, C_MOUNTAIN, char(2, 0, 0)["c"], char(2, 0, 1)["c"]]}
    for size, name in ((WIDE, "wide"), (NARROW, "narrow")):
        pg = Page(browser, size, state=seeded("age-5-6", chars))
        p = pg.open()
        p.click(".home-actions .btn.berry")
        p.wait_for_selector(".box-tabs")
        check(p.inner_text(".box-total") == fmt(UI["boxTotal"], n=5, m=1000), f"total line: {p.inner_text('.box-total')}")
        tabs = p.eval_on_selector_all(".box-tabs .btn", "(bs) => bs.map((b) => [b.getAttribute('aria-selected'), b.innerText])")
        check(len(tabs) == 4 and tabs[2][0] == "true", f"current library tab not selected: {tabs}")
        check("2 / 300" in tabs[2][1] and "3 / 150" in tabs[0][1], f"tab counts wrong: {tabs}")
        check(p.locator(".box-group").count() == 30, "5-6 tab should list 30 groups")
        pg.shot(f"box-{name}")
        p.locator(".box-tabs .btn").first.click()
        p.wait_for_selector(".box-row")
        check(p.locator(".box-group").count() == 15, "3-4 tab should list 15 groups")
        tile = p.locator(".box-row .tzg").first
        box = tile.bounding_box()
        p.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        p.mouse.down()
        time.sleep(0.8)
        check(p.locator(".py-pop").count() == 1 and p.inner_text(".py-pop") == char(0, 0, 0)["py"], "long press did not show pinyin")
        pg.said()
        p.mouse.up()
        time.sleep(0.2)
        check(not pg.said(), "long press also spoke the character")
        pg.shot(f"box-pinyin-{name}")
        pg.close()


def t_kept(browser):
    """v1 behavior still in place: rest screen and parent extension, dark mode, reduced motion."""
    pg = Page(browser, NARROW, session_used=16 * 60 * 1000)
    p = pg.p
    p.goto(BASE)
    p.wait_for_selector(".end .parent")
    check(UI["restTitle"] in p.inner_text(".end"), "rest screen missing after the time limit")
    pg.shot("rest-narrow")
    p.focus(".end .parent")
    p.keyboard.press("Shift+Enter")
    p.wait_for_selector(".home-actions")
    pg.close()

    pg = Page(browser, NARROW, color_scheme="dark")
    p = pg.open()
    check(p.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(15, 37, 48)", "dark theme not applied")
    pick_library(p, "age-6-7")
    open_group(p, 0)
    pg.shot("group-67-dark")
    pg.close()

    pg = Page(browser, WIDE, reduced_motion="reduce")
    p = pg.open()
    open_group(p, 0)
    open_act(p, UI["listen"])
    p.wait_for_selector(".opt")
    for i in range(4):
        if p.locator(".opt.right").count():
            break
        if not p.locator(".opt").nth(i).is_disabled():
            p.locator(".opt").nth(i).click()
    check(p.locator(".fx").count() == 0, "particles shown with reduced motion")
    pg.close()


def t_daily_new(browser):
    """The parent's daily-new setting overrides the library default and survives reopening."""
    pg = Page(browser, NARROW)
    p = pg.open()
    open_settings(p)
    opts = p.eval_on_selector_all(settings_select(p, "dailyNew") + " option", "(os) => os.map((o) => o.value)")
    check(opts == [str(n) for n in range(1, 11)], f"daily new choices should be 1-10: {opts}")
    p.select_option(settings_select(p, "dailyNew"), "7")
    pg.shot("settings-daily-new")
    p.click(".panel .btn.leaf")
    open_settings(p)
    check(p.input_value(settings_select(p, "dailyNew")) == "7", "daily new setting lost")
    p.click(".panel .btn.leaf")
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".learn-card")
    check(learn_chars(p) == [char(0, 0, k)["c"] for k in range(7)], "daily practice did not teach 7 new characters")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    p.click(".home-actions .btn.sun")
    time.sleep(0.5)
    check(p.locator(".learn-card").count() == 0, "more new characters than the daily setting")
    pg.close()


def t_switch(browser):
    """After today's new characters in 3-4, switching to 5-6 brings 5-6 new characters, even with reviews due."""
    lots_due = {char(0, g, k)["c"]: {"l": 2, "d": 0, "n": True, "r": 2, "w": 0} for g in (1, 2) for k in range(10)}
    pg = Page(browser, WIDE, state=seeded("age-3-4", lots_due, new_today=profile(0)["dailyNew"]))
    p = pg.open()
    pick_library(p, "age-5-6")
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".learn-card")
    fresh = [char(2, 0, k)["c"] for k in range(profile(2)["dailyNew"])]
    check(learn_chars(p) == fresh, "switching library did not bring its new characters")
    p.locator(".learn-nav .btn").last.click()
    lib56 = {x["c"] for g in LIBS[2]["groups"] for x in g["chars"]}
    lib34 = {x["c"] for g in LIBS[0]["groups"] for x in g["chars"]}
    seen_new = 0
    for _ in range(40):
        if not p.locator(".opt").count():
            break
        opts = p.eval_on_selector_all(".opt", "(os) => os.map((o) => o.getAttribute('aria-label'))")
        target = next((o for o in opts if o in fresh), None)
        if target and sum(o in lib56 for o in opts) == 4:
            seen_new += 1
        # answer by trying options until one is right
        for i in range(4):
            if p.locator(".opt.right").count():
                break
            if not p.locator(".opt").nth(i).is_disabled():
                p.locator(".opt").nth(i).click()
        time.sleep(1.9)
    check(seen_new >= 1, "no quiz round showed the new 5-6 characters with 5-6 options")
    check(pg.state()["newLog"]["byLib"].get("age-5-6") == len(fresh), "5-6 allowance not counted separately")
    pg.close()


KIDS_KEY = "hanzi-garden-kids-v1"
with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
    _h = f.read()
_s = _h.index('id="content">') + len('id="content">')
AVATARS = json.loads(_h[_s:_h.index("</script>", _s)])["avatars"]


def ls(p, key):
    raw = p.evaluate(f"localStorage.getItem({json.dumps(key)})")
    return json.loads(raw) if raw else None


def kid_buttons(p):
    return p.eval_on_selector_all(".kid-btn[data-kid]", "(bs) => bs.map((b) => [b.dataset.kid, b.getAttribute('aria-pressed')])")


def t_kids(browser):
    """Several children: existing progress becomes child 1 untouched; each child has own progress,
    library, stars and session timer; speech rate is shared; removing a child deletes only theirs."""
    pg = Page(browser, NARROW, state=V1_STATE)
    p = pg.open()
    check(p.locator(".kid-badge").count() == 0, "avatar shown with a single child")
    reg = ls(p, KIDS_KEY)
    check(reg["current"] == "p1" and reg["list"] == [{"id": "p1", "avatar": AVATARS[0]}], f"registry: {reg}")
    before = p.evaluate(f"localStorage.getItem({json.dumps(LS_KEY)})")

    # Add a second child, pick 5-6 for them and change the shared speech rate.
    open_settings(p)
    p.click(".kid-btn.add")
    p.wait_for_selector(".panel")
    check(kid_buttons(p) == [["p1", "false"], ["p2", "true"]], f"kid buttons: {kid_buttons(p)}")
    p.click('.lib-card[data-lib="age-5-6"]')
    p.eval_on_selector(".panel input[type=range]",
                       "(r) => { r.value = '1.1'; r.dispatchEvent(new Event('input')); r.dispatchEvent(new Event('change')); }")
    pg.shot("settings-kids")
    p.click(f".panel .btn.leaf:has-text('{UI['confirm']}')")
    p.wait_for_selector(".home-actions")
    check(p.inner_text("#starCount").strip().endswith("0"), "new child should start with 0 stars")
    check(LIBS[2]["name"] in p.inner_text(".lib-tag"), "new child's library not applied")
    check(p.inner_text(".kid-badge") == AVATARS[1], "second child's avatar not on home")
    pg.shot("home-kid2")
    check(p.evaluate(f"localStorage.getItem({json.dumps(LS_KEY)})") == before, "first child's progress was rewritten")
    check(ls(p, LS_KEY + "-p2")["settings"]["libraryId"] == "age-5-6", "second child's progress not stored separately")

    # Child 1 has used up their time today; child 2 has not. Switching back shows child 1's rest screen.
    p.evaluate("localStorage.setItem('hanzi-garden-session-v1', JSON.stringify({used: 16 * 60000, last: Date.now()}))")
    open_settings(p)
    p.click('.kid-btn[data-kid="p1"]')
    p.wait_for_selector('.kid-btn[data-kid="p1"][aria-pressed="true"]')
    check(p.input_value(".panel input[type=range]") == "1.1", "speech rate is not shared between children")
    check(p.get_attribute('.lib-card[data-lib="age-3-4"]', "aria-checked") == "true", "first child's library lost")
    p.click(f".panel .btn.leaf:has-text('{UI['confirm']}')")
    p.wait_for_selector(".end .parent")
    check(p.inner_text("#starCount").strip().endswith("12"), "first child's stars lost")
    p.focus(".end .parent")
    p.keyboard.press("Shift+Enter")
    p.wait_for_selector(".home-actions")

    # Remove child 2 (needs a second press): only their data goes.
    open_settings(p)
    p.click('.kid-btn[data-kid="p2"]')
    p.wait_for_selector('.kid-btn[data-kid="p2"][aria-pressed="true"]')
    btn = p.locator(f".panel .btn:has-text('{UI['removeKid']}')")
    btn.click()
    p.locator(f".panel .btn:has-text('{UI['removeKidConfirm']}')").click()
    p.wait_for_selector(".home-actions")
    check(ls(p, KIDS_KEY)["list"] == [{"id": "p1", "avatar": AVATARS[0]}], "child not removed from the list")
    check(ls(p, LS_KEY + "-p2") is None, "removed child's progress still stored")
    check(ls(p, LS_KEY)["stars"] == 12, "first child's progress affected by removal")
    check(p.locator(".kid-badge").count() == 0, "avatar still shown with one child left")
    pg.close()


def t_reset_lib(browser):
    """Clearing one library removes its characters and the stars earned there; other libraries stay."""
    other = char(2, 0, 0)["c"]
    rec = {"l": 3, "d": 9e15, "n": True, "r": 3, "w": 0}
    st = seeded("age-3-4", {C1: dict(rec), C2: dict(rec), other: dict(rec)})
    st["stars"], st["starsByLib"] = 20, {"age-3-4": 7, "age-5-6": 3}
    pg = Page(browser, NARROW, state=st)
    p = pg.open()
    open_settings(p)
    label = fmt(UI["resetLib"], name=LIBS[0]["name"])
    p.locator(f".panel .btn:has-text('{label}')").click()
    p.locator(f".panel .btn:has-text('{UI['resetConfirm']}')").first.click()
    p.wait_for_selector(".home-actions")
    s = pg.state()
    check(C1 not in s["chars"] and C2 not in s["chars"], "3-4 characters not cleared")
    check(other in s["chars"], "5-6 character cleared too")
    check(s["stars"] == 13 and "age-3-4" not in s["starsByLib"] and s["starsByLib"]["age-5-6"] == 3, f"stars after reset: {s['stars']} {s['starsByLib']}")
    check(p.inner_text("#starCount").strip().endswith("13"), "star counter not updated")

    # A star earned now is attributed to the answer's library.
    open_group(p, 0)
    group = [x for x in LIBS[0]["groups"][0]["chars"]]
    open_act(p, UI["listen"])
    time.sleep(0.8)
    said = pg.said()
    target = next(x["c"] for x in group if any(fmt(UI["promptWordOf"], c=x["c"], w=x["w"]) == t for t in said))
    p.click(f'.opt[aria-label="{target}"]')
    time.sleep(1.2)
    check(pg.state()["starsByLib"].get("age-3-4") == 1, f"star not counted for 3-4: {pg.state()['starsByLib']}")
    pg.close()


CHECKS = {
    "load": t_load,
    "font": t_font,
    "migration": t_migration,
    "offline": t_offline,
    "games34": t_games_3_4,
    "libraries": t_libraries,
    "unlock": t_unlock,
    "daily": t_daily,
    "dailynew": t_daily_new,
    "switch": t_switch,
    "nopic": t_nopic,
    "fill": t_fill,
    "speech": t_speech,
    "box": t_box,
    "kept": t_kept,
    "kids": t_kids,
    "resetlib": t_reset_lib,
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
