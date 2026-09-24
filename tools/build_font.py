"""Build fonts/kai.woff2: a subset of LXGW WenKai GB (textbook-standard Kai forms) for Hanzi Garden.

Only the glyphs the app draws in the Kai face are kept: every character and example word in
data/charsets.json, the app title, and the blank mark used on listening cards.

Source font (not committed; ~25 MB), from https://github.com/lxgw/LxgwWenkaiGB/releases:
  gh release download -R lxgw/LxgwWenkaiGB -p LXGWWenKaiGB-Regular.ttf -D tools/font-src

Usage:
  pip install fonttools brotli
  python tools/build_font.py        # run again whenever data/charsets.json changes

License: SIL OFL 1.1 (fonts/OFL.txt). Its additional permission allows subsetting to WOFF2
for web font delivery.
"""
import json
import os

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCE = os.path.join(HERE, "font-src", "LXGWWenKaiGB-Regular.ttf")
OUT = os.path.join(ROOT, "fonts", "kai.woff2")
EXTRA = "○"  # blank mark on listening cards


def needed_text():
    with open(os.path.join(ROOT, "data", "charsets.json"), encoding="utf-8") as f:
        data = json.load(f)
    text = set(EXTRA)
    for lib in data["libraries"]:
        for g in lib["groups"]:
            for x in g["chars"]:
                text.update(x["c"] + x["w"])
    with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
        html = f.read()
    start = html.index('id="content">') + len('id="content">')
    ui = json.loads(html[start:html.index("</script>", start)])["ui"]
    text.update(ui["appTitle"])
    return "".join(sorted(text))


def main():
    text = needed_text()
    cmap = TTFont(SOURCE).getBestCmap()
    missing = [ch for ch in text if ord(ch) not in cmap]
    if missing:
        raise SystemExit(f"source font lacks: {''.join(missing)}")
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]  # keep copyright and license entries
    font = subset.load_font(SOURCE, opts)
    sub = subset.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(font)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    subset.save_font(font, OUT, opts)
    print(f"{len(text)} glyphs -> fonts/kai.woff2 ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
