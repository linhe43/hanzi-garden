# CLAUDE.md

Hanzi Garden (识字小花园): a kids' Chinese character-learning PWA. Design and rationale live in README.md (v1) and IMPLEMENTATION.md (v2 age libraries); this file holds only the rules to follow when changing code.

## Rules

- **No personal data, ever.** Never ask for or store age, birthdate, name, or any other personal information. Age only appears as the name of a library the parent picks.
- **No build.** The app is `index.html` (vanilla JS + CSS) plus `data/charsets.json` and `fonts/kai.woff2`. Don't add frameworks, bundlers, or npm dependencies. External resources: Google Fonts only.
- **Bump the cache.** Any change to a cached file (`index.html`, `data/charsets.json`, `fonts/kai.woff2`, `privacy.html`, manifest, icons) → bump `CACHE` in `sw.js` (`hanzi-garden-v4` → `v5`). The service worker serves these cache-first, so without a bump devices keep the old copy. New files needed offline must also go into `CORE`.
- **Content vs. code.** Chinese text lives only in `data/charsets.json` and the `<script type="application/json" id="content">` block (`ui` for interface strings). Code, comments, and string literals stay English.
- **Charsets are generated.** Don't edit `data/charsets.json` by hand: change `tools/hand_libraries.json`, `tools/lib56_67.txt`, or `tools/pinyin_overrides.json`, then run `python tools/build_charsets.py --review` and `python tools/build_font.py` (the font subset must cover every character and word). Per-library behavior comes from the `profile` (set in the script's `PROFILES`); never hard-code age rules in the app.
- **Kai font.** Characters render in `HG Kai`, a subset of LXGW WenKai GB (mainland textbook forms) on every device, including Windows. Don't swap in Google Fonts Kai faces: LXGW WenKai TC uses Taiwan forms (眞, 戶) and Ma Shan Zheng is brush calligraphy. Keep `fonts/OFL.txt` next to the font.
- **Served over http(s) only.** The app fetches `data/charsets.json`, so opening `index.html` via `file://` no longer works. Use `python -m http.server` locally.
- **Screens.** Navigate via `show(screen, ...args)`. Each screen registers a cleanup that clears its timers, animation frames, and listeners — keep that when adding screens.
- **Store package.** `name`, `short_name`, and `icons` in `manifest.webmanifest` must not change — the Microsoft Store package (PWABuilder) would need repackaging. Everything else updates through GitHub Pages.
- **Ask first** before changing the spaced-repetition algorithm, removing a feature, changing library content, or splitting the file structure.
- **Audience is young kids.** Big tap targets, animated (not text) feedback, no time pressure; the session timer never interrupts a round in progress.
- **Testing.** `python -m http.server 8765 --bind 127.0.0.1`, then `python tests/smoke.py` (Playwright for Python, uses the installed Edge). Covers 1366×768 and 390×844; screenshots land in `tests/out/`.

## Current status

Update in place; don't append history (that goes in git commits / README 迭代记录).

- Live on GitHub Pages: https://linhe43.github.io/hanzi-garden/ and in the Microsoft Store (PWABuilder package loading that URL).
- v2: four parent-selected age libraries (3–4, 4–5, 5–6, 6–7), 1000 characters, fill-in-the-word game.
- Not done: placement quiz (测一测), example sentences (`s` field), libraries beyond age 7, iOS store listing.
