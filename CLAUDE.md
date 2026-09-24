# CLAUDE.md

Hanzi Garden (识字小花园): a kids' Chinese character-learning PWA. Design and rationale live in README.md; this file holds only the rules to follow when changing code.

## Rules

- **Single file, no build.** The whole app is `index.html` (vanilla JS + CSS). Don't add frameworks, bundlers, or npm dependencies.
- **Bump the cache.** Any change to a cached file (`index.html`, `privacy.html`, manifest, icons) → bump `CACHE` in `sw.js` (`hanzi-garden-v1` → `v2`). New files needed offline must also go into `CORE`.
- **Content vs. code.** All Chinese text (characters, UI strings, praise, garden plants) lives in the `<script type="application/json">` block. Code, comments, and identifiers stay English. New stages = append to `stages`, no code changes.
- **Screens.** Navigate via `show(screen, ...args)`. Each screen registers a cleanup that clears its timers, animation frames, and listeners — keep that when adding screens.
- **Manifest `name`** (`识字小花园`) must match the Microsoft Store reserved name exactly. Don't rename casually.
- **Audience is young kids.** Big tap targets, animated (not text) feedback, no time pressure; the session timer never interrupts a round in progress.
- **Testing.** Playwright headless at a wide and a phone viewport; walk through each game mode and check screenshots.

## Current status

Update in place; don't append history (that goes in git commits / README 迭代记录).

- Live on GitHub Pages: https://linhe43.github.io/hanzi-garden/
- Stage 1 (100 characters, 10 levels) complete; stage 2 not started.
- Microsoft Store: developer account, name reservation, and PWABuilder packaging not done yet.
