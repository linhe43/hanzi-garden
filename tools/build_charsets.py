"""Build data/charsets.json for Hanzi Garden.

Inputs (both hand-curated):
  tools/hand_libraries.json  ages 3-4 and 4-5: char, pinyin, word, emoji picture
  tools/lib56_67.txt         ages 5-6 and 6-7: char:word pairs, 10 per group

For the text-format libraries, pinyin is derived from the example word with
pypinyin, so polyphonic characters get the reading used in that word.
tools/pinyin_overrides.json fixes cases where the word reading is a neutral tone or
pypinyin is known to be wrong.

Usage:
  pip install pypinyin
  python tools/build_charsets.py            # writes data/charsets.json
  python tools/build_charsets.py --review   # also lists polyphonic characters to double-check
"""
import json
import os
import sys

from pypinyin import Style, pinyin

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# char -> pinyin shown on the card (citation reading when the word gives a neutral tone)
with open(os.path.join(HERE, "pinyin_overrides.json"), encoding="utf-8") as f:
    PINYIN_OVERRIDES = json.load(f)

# Per-library behavior. The app reads these instead of hard-coding age rules.
#   dailyNew        max new characters introduced by daily practice per calendar day
#   sessionMin      default session length when the parent switches to this library
#   showPinyin      default for the pinyin line on learn cards
#   speech          "wordOf": char + "word-of-char" phrasing; "charWord": char then word (for function words)
#   games           activity ids shown on the group screen, in order
PROFILES = {
    "age-3-4": {"dailyNew": 1, "sessionMin": 10, "showPinyin": False, "speech": "wordOf",
                "games": ["learn", "flowers", "picture", "memory", "listen"]},
    "age-4-5": {"dailyNew": 1, "sessionMin": 10, "showPinyin": False, "speech": "wordOf",
                "games": ["learn", "flowers", "listen", "picture", "memory"]},
    "age-5-6": {"dailyNew": 1, "sessionMin": 15, "showPinyin": False, "speech": "charWord",
                "games": ["learn", "listen", "fill", "memory", "flowers"]},
    "age-6-7": {"dailyNew": 2, "sessionMin": 15, "showPinyin": True, "speech": "charWord",
                "games": ["learn", "listen", "fill", "memory", "flowers"]},
}


def word_pinyin(ch, word):
    if ch in PINYIN_OVERRIDES:
        return PINYIN_OVERRIDES[ch]
    return pinyin(word, style=Style.TONE)[word.index(ch)][0]


def load_text_libraries(path):
    libraries, current = [], None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("@"):
                lib_id, name, desc = line[1:].split("|")
                current = {"id": lib_id, "name": name, "desc": desc, "groups": []}
                libraries.append(current)
                continue
            name, icon, items = line.split("|")
            chars = []
            for item in items.split():
                ch, word = item.split(":")
                chars.append({"c": ch, "py": word_pinyin(ch, word), "w": word, "pic": None})
            current["groups"].append({"name": name, "icon": icon, "chars": chars})
    return libraries


def load_hand_libraries(path):
    with open(path, encoding="utf-8") as f:
        hand = json.load(f)
    return [{
        "id": lib_id, "name": lib["name"], "desc": lib["desc"],
        "groups": [{"name": g["name"], "icon": g["icon"],
                    "chars": [{"c": c, "py": py, "w": w, "pic": pic} for c, py, w, pic in g["chars"]]}
                   for g in lib["groups"]],
    } for lib_id, lib in hand.items()]


def validate(libraries):
    seen = {}
    for lib in libraries:
        for g in lib["groups"]:
            if len(g["chars"]) != 10:
                raise SystemExit(f"{lib['id']}/{g['name']}: expected 10 characters, got {len(g['chars'])}")
            for x in g["chars"]:
                if x["c"] not in x["w"]:
                    raise SystemExit(f"{x['c']} does not appear in its word {x['w']}")
                if x["c"] in seen:
                    raise SystemExit(f"{x['c']} appears in both {seen[x['c']]} and {lib['id']}")
                seen[x["c"]] = lib["id"]
    return len(seen)


def review(libraries):
    print("\nPolyphonic characters (check the reading fits the word):")
    for lib in libraries:
        for g in lib["groups"]:
            for x in g["chars"]:
                readings = pinyin(x["c"], style=Style.TONE, heteronym=True)[0]
                if len(readings) > 1:
                    print(f"  {lib['id']:8} {x['c']} {x['py']:7} {x['w']:6} all: {'/'.join(readings)}")


def main():
    libraries = load_hand_libraries(os.path.join(HERE, "hand_libraries.json"))
    libraries += load_text_libraries(os.path.join(HERE, "lib56_67.txt"))
    total = validate(libraries)
    for lib in libraries:
        lib["profile"] = PROFILES[lib["id"]]
    out = {"version": 2, "libraries": libraries}
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "charsets.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for lib in libraries:
        n = sum(len(g["chars"]) for g in lib["groups"])
        print(f"{lib['id']}: {lib['name']} {n} chars, {len(lib['groups'])} groups")
    print(f"total {total} unique characters -> data/charsets.json")
    if "--review" in sys.argv:
        review(libraries)


if __name__ == "__main__":
    main()
