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


def charsets():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "data", "charsets.json"), encoding="utf-8") as f:
        return json.load(f)


def open_settings(p):
    """Parent settings need a 2-second hold; Shift+Enter is the keyboard equivalent."""
    p.focus(".home-foot .parent")
    p.keyboard.press("Shift+Enter")
    p.wait_for_selector(".panel")


def pick_library(p, lib_id):
    open_settings(p)
    p.click(f'.lib-card[data-lib="{lib_id}"]')
    p.wait_for_selector(".home-actions")


GAME_LABEL = {"learn": "学新字", "listen": "听音找字", "picture": "看图找字", "memory": "翻牌配对",
              "flowers": "浇花开花", "fill": "选字填词"}
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
        check(p.inner_text(".gcard .num") == "第1关", "level numbers do not restart per library")
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
    p.select_option(".panel label:has-text('每次学习时间') select", "30")
    p.click(".panel label.inline input >> nth=0")
    p.click(".panel .btn.leaf")
    open_settings(p)
    check(p.input_value(".panel label:has-text('每次学习时间') select") == "30", "manual session length lost")
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
    """A v2 state on library lib_id with the given per-character records."""
    return {"v": 2, "stars": 0, "updatedAt": 1, "chars": chars,
            "settings": {"rate": 0.8, "voice": "", "unlockAll": False, "sessionMin": 15, "libraryId": lib_id, "showPinyin": False},
            "newLog": {"day": time.strftime("%Y-%m-%d"), "count": new_today}}


def learn_chars(p):
    """Characters shown on the learn cards, stepping through with 'next'."""
    seen = []
    while True:
        seen.append(p.inner_text(".learn-box .han"))
        nxt = p.locator(".learn-nav .btn").last
        if "学完啦" in nxt.inner_text():
            return seen
        nxt.click()


def t_daily(browser):
    data = charsets()
    lib34, lib45 = data["libraries"][0], data["libraries"][1]
    # 1) 3-4 library, dailyNew = 1: first run introduces exactly one character, the second run none.
    pg = Page(browser, WIDE)
    p = pg.open()
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".learn-card")
    check(learn_chars(p) == [lib34["groups"][0]["chars"][0]["c"]], "first daily run should teach the first character only")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    p.click(".home-actions .btn.sun")
    time.sleep(0.5)
    check(p.locator(".learn-card").count() == 0, "second daily run on the same day introduced new characters")
    check(pg.state()["newLog"]["count"] == 1, "newLog not counted")
    pg.close()

    # 2) Review is global: on 4-5 with today's new allowance used up, a due 3-4 character is still reviewed.
    pg = Page(browser, WIDE, state=seeded("age-4-5", {"水": {"l": 2, "d": 0, "n": True, "r": 2, "w": 0}}, new_today=1))
    p = pg.open()
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".options")
    opts = p.eval_on_selector_all(".opt", "(os) => os.map((o) => o.getAttribute('aria-label'))")
    check("水" in opts and p.locator(".learn-card").count() == 0, f"due 3-4 character not reviewed on 4-5: {opts}")
    pg.close()

    # 3) Finished library: new characters come from the next library; the home note shows once.
    done = {x["c"]: {"l": 3, "d": 9e15, "n": True, "r": 3, "w": 0} for g in lib34["groups"] for x in g["chars"]}
    pg = Page(browser, NARROW, state=seeded("age-3-4", done))
    p = pg.open()
    check(p.locator(".lib-done").count() == 1, "library-finished note missing")
    pg.shot("home-lib-done")
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".learn-card")
    check(learn_chars(p) == [lib45["groups"][0]["chars"][0]["c"]], "new character not taken from the next library")
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
    check("看图找字" not in act_labels(p), "picture quiz shown for a group without pictures")
    open_act(p, "学新字")
    check(p.locator(".learn-word").count() == 1 and p.locator(".learn-pic").count() == 0, "learn card should show the big word")
    check(p.locator(".learn-info .word").count() == 1, "word shown twice on the learn card")
    pg.shot("learn-56")
    back(p)
    open_act(p, "翻牌配对")
    says = p.eval_on_selector_all(".mcard .say", "(ss) => ss.map((s) => s.textContent)")
    hans = p.eval_on_selector_all(".mcard .front .han", "(ss) => ss.map((s) => s.textContent)")
    check(len(says) == 4 and len(hans) == 4, f"round 1 should have 4 listening + 4 character cards: {says} {hans}")
    for c in hans:
        check(any("○" in s and c not in s.replace("🔊", "") for s in says), f"listening card leaks the character {c}: {says}")
    pg.shot("memory-56")
    back(p)
    open_act(p, "听音找字")
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
    open_act(p, "看图找字")
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
    open_act(p, "选字填词")
    for _ in range(len(group)):
        p.wait_for_selector(".fill-word")
        shown = p.eval_on_selector(".fill-word", "(w) => [...w.children].map((k) => k.classList.contains('tzg') ? '_' : k.textContent).join('')")
        opts = p.eval_on_selector_all(".opt", "(os) => os.map((o) => o.getAttribute('aria-label'))")
        # 我的 and 我们 both show as 我_; the answer is the option whose word matches.
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
    # On 5-6, reviewing 木 (3-4, wordOf) still says "木，木头的木"; 了 (5-6, charWord) says "了，好了".
    pg = Page(browser, WIDE, state=seeded("age-5-6", {"木": {"l": 2, "d": 0, "n": True, "r": 2, "w": 0}}, new_today=1))
    p = pg.open()
    p.click(".home-actions .btn.sun")
    p.wait_for_selector(".options")
    time.sleep(0.6)
    p.click('.opt[aria-label="木"]')
    time.sleep(0.3)
    said = pg.said()
    check("木，木头的木" in said, f"wordOf template not used for 木: {said}")
    check(all("好了" not in t for t in said), "wrong character spoken")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    open_group(p, 0)
    pg.said()
    p.click('.char-row .tzg:has-text("了")')
    time.sleep(0.3)
    check("了，好了" in pg.said(), "charWord template not used for 了")
    open_act(p, "听音找字")
    time.sleep(0.6)
    check(any(t.startswith("找一找：") for t in pg.said()), "charWord prompt template not used")
    pg.close()

    # Pinyin: off by default on 3-4, on after the toggle.
    pg = Page(browser, WIDE)
    p = pg.open()
    open_group(p, 0)
    open_act(p, "学新字")
    check(p.locator(".learn-card .pinyin").count() == 0, "pinyin shown while the toggle is off")
    p.goto(BASE)
    p.wait_for_selector(".home-actions")
    open_settings(p)
    p.click(".panel label.inline input >> nth=0")
    p.click(".panel .btn.leaf")
    open_group(p, 0)
    open_act(p, "学新字")
    check(p.locator(".learn-card .pinyin").count() == 1, "pinyin hidden while the toggle is on")
    pg.close()


def t_box(browser):
    """Treasure box: total line, one tab per library opening on the current one, long press shows pinyin."""
    rec = {"l": 3, "d": 9e15, "n": True, "r": 3, "w": 0}
    chars = {c: dict(rec) for c in ["一", "二", "山", "是", "不"]}
    for size, name in ((WIDE, "wide"), (NARROW, "narrow")):
        pg = Page(browser, size, state=seeded("age-5-6", chars))
        p = pg.open()
        p.click(".home-actions .btn.berry")
        p.wait_for_selector(".box-tabs")
        check(p.inner_text(".box-total") == "一共认识 5 个字 / 1000", f"total line: {p.inner_text('.box-total')}")
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
        check(p.locator(".py-pop").count() == 1 and p.inner_text(".py-pop") == "yī", "long press did not show pinyin")
        pg.said()
        p.mouse.up()
        time.sleep(0.2)
        check(not pg.said(), "long press also spoke the character")
        pg.shot(f"box-pinyin-{name}")
        pg.close()


CHECKS = {
    "load": t_load,
    "migration": t_migration,
    "offline": t_offline,
    "games34": t_games_3_4,
    "libraries": t_libraries,
    "unlock": t_unlock,
    "daily": t_daily,
    "nopic": t_nopic,
    "fill": t_fill,
    "speech": t_speech,
    "box": t_box,
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
