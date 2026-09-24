# 识字小花园 v2：按年龄分字库 · 实现说明

这份文档说明如何把现在的「单一 100 字阶段」改成「家长按年龄选择字库」。字库一共 4 个，累计 1000 字。文档里的步骤按提交顺序排列，每一步都能单独测试。可以自己按步骤改，也可以把整份文档交给 VS Code 里的 Claude Code 逐步执行。

约定（沿用 v1）：

- **代码里只用英文**，包括变量名、注释和字符串字面量。
- **所有中文放在数据里**：字库放在 `data/charsets.json`；界面文字放在 `index.html` 的 `<script type="application/json" id="content">` 数据块里（v1 的 `ui` 部分）。

---

## 0. 这次要做什么

| 需求 | 做法 |
|---|---|
| 家长自己选字库，不填出生年月 | 家长设置里列出 4 个字库，单选 |
| 字库按年龄命名，字数不同 | 3–4岁 150 字、4–5岁 150 字、5–6岁 300 字、6–7岁 400 字，累计 1000 字 |
| 不同年龄的学法不同 | 每个字库带一份 `profile`：每天新字数、默认时长、是否显示拼音、朗读方式、玩法顺序 |
| 没有图的字也能学 | 学字卡用「大号词语」代替图；看图找字只在有图的组里出现；翻牌用「听音卡」代替图卡 |
| 抽象字要有合适的练法 | 新增玩法「选字填词」（`fill`） |

**不改的部分**：间隔复习算法、星星和花园、动画反馈、15 分钟时长控制、PWA 和商店配置。进度按「字」来存，所以旧版的 100 字进度会自动归到 3–4 岁字库，不会丢。

---

## 1. 仓库结构

```
hanzi-garden/
├── index.html
├── manifest.webmanifest
├── sw.js
├── privacy.html
├── icon-*.png
├── screenshots/
├── data/
│   └── charsets.json          ← 新增：由脚本生成，不要手改
├── tools/                     ← 新增：字库源文件和生成脚本
│   ├── build_charsets.py
│   ├── hand_libraries.json    （3–4岁、4–5岁：字、拼音、例词、emoji）
│   ├── pinyin_overrides.json  （多音字、轻声的读音修正）
│   └── lib56_67.txt           （5–6岁、6–7岁：字:例词，拼音由脚本生成）
├── CHARSETS.md                ← 新增：1000 字的可读清单，方便审阅
└── IMPLEMENTATION.md          ← 本文档
```

`tools/` 和 `CHARSETS.md` 放进公开仓库没有问题，GitHub Pages 会一起发布，但 app 不会用到它们。

---

## 2. 数据格式：`data/charsets.json`

```json
{
  "version": 2,
  "libraries": [
    {
      "id": "age-3-4",
      "name": "3–4岁字库",
      "desc": "看得见、画得出的字……",
      "profile": {
        "dailyNew": 3,
        "sessionMin": 10,
        "showPinyin": false,
        "speech": "wordOf",
        "games": ["learn", "flowers", "picture", "memory", "listen"]
      },
      "groups": [
        {
          "name": "数一数",
          "icon": "🔢",
          "chars": [
            { "c": "一", "py": "yī", "w": "一个", "pic": "🍓" }
          ]
        }
      ]
    }
  ]
}
```

| 字段 | 含义 |
|---|---|
| `c` | 字。全部 1000 个字互不重复，脚本会检查 |
| `py` | 这个字在例词里的读音。多音字按例词取读音，例如 `还` 取 hái、`种` 取 zhǒng |
| `w` | 例词，一定包含 `c` |
| `pic` | emoji 图；5–6岁、6–7岁字库里是 `null` |
| `profile.dailyNew` | 「今日练习」每个自然日最多引入几个新字 |
| `profile.sessionMin` | 切换到这个字库时，建议的每次时长 |
| `profile.showPinyin` | 切换到这个字库时，拼音开关的默认值 |
| `profile.speech` | `wordOf` 读作「木，木头的木」；`charWord` 读作「了，好了」（虚词用 wordOf 会很别扭） |
| `profile.games` | 关卡页显示哪些玩法、按什么顺序 |

**修改字库**：编辑 `tools/hand_libraries.json` 或 `tools/lib56_67.txt`，然后运行：

```bash
pip install pypinyin
python tools/build_charsets.py --review
```

脚本会检查：每组正好 10 个字、字在例词里、全库没有重复字。加上 `--review` 还会列出所有多音字，方便人工核对读音。读音不对时，在 `tools/pinyin_overrides.json` 里修正。

---

## 3. 实现步骤

### Step 1 · 从文件加载字库

1. 从 `index.html` 的内嵌 JSON 里删掉 `stages`，只保留 `ui`、`praise`、`retry`、`flowers`、`bugs`、`garden`。
2. 启动时先 `fetch('data/charsets.json')` 读取字库，再渲染首页。加载期间显示一个简单的加载状态，比如首页的田字格标题。
3. 把原来按 `stages` 展开 `GROUPS`、`CHAR`、`ALL` 的代码，改成按 `libraries` 展开：

```js
// Build lookup tables from the loaded charsets.
const LIBS = data.libraries;                       // ordered: age-3-4 ... age-6-7
const CHAR = new Map();                            // char -> { c, py, w, pic, lib, group }
LIBS.forEach((lib, li) => lib.groups.forEach((g, gi) =>
  g.chars.forEach((x) => CHAR.set(x.c, { ...x, lib: li, group: gi }))));
const ALL = [...CHAR.keys()];
const currentLib = () => LIBS.find((l) => l.id === state.settings.libraryId) || LIBS[0];
```

4. 在 `sw.js` 的 `CORE` 里加上 `'./data/charsets.json'`，并把 `CACHE` 改成 `hanzi-garden-v2`。

> 注意：`fetch` 在 `file://` 下不能用。以后统一从 GitHub Pages 的网址打开，或者安装成 PWA / 商店版。之前那种桌面快捷方式直接打开本地文件的用法，会读不到字库。

**验收**：打开页面后能进入首页；F12 → Network 里能看到 `charsets.json` 返回 200；断网刷新后仍能打开。

### Step 2 · 进度数据迁移（v1 → v2）

在 `normalize(state)` 里补上新字段，旧数据照样能读：

```js
// Defaults added in v2. Per-character progress is keyed by character, so v1 progress carries over.
settings.libraryId ??= 'age-3-4';
settings.showPinyin ??= false;
state.newLog ??= { day: '', count: 0 };   // new characters introduced by daily practice today
state.v = 2;
```

`state.chars` 的结构不变。**验收**：用旧版玩过的浏览器打开新版，星星和字宝箱里的颜色都还在。

### Step 3 · 家长设置：选字库

在家长设置面板的最上面，加一组单选卡片，每个字库一张：

- 卡片显示：字库名、简介、字数、已学进度（例如「已认识 42 / 150」）。
- 选中某个字库时：
  1. `settings.libraryId = lib.id`
  2. `settings.dailyNew = lib.profile.dailyNew`
  3. `settings.sessionMin = lib.profile.sessionMin`
  4. `settings.showPinyin = lib.profile.showPinyin`
  5. `save()`。面板**不关闭**，下面的控件立即显示这个字库的默认值，家长可以接着改，点「确认」后关闭面板并重新渲染首页。

字库卡片下面依次是：「每天学几个新字」（1–5，绑定 `settings.dailyNew`，为空时用当前字库的 `profile.dailyNew`）、「每次学习时间」、「显示拼音」开关（绑定 `settings.showPinyin`）。

需要新增的界面文字（放进 `ui`）：

```json
"library": "字库",
"libraryProgress": "已认识 {n} / {m}",
"showPinyin": "显示拼音",
"currentLib": "{name} · {n}/{m}"
```

### Step 4 · 首页、地图和关卡只显示当前字库

- **首页**：在标题下面加一个小标签，显示 `currentLib` 文案，例如「3–4岁字库 · 42/150」。点击无效果，切换字库只能在家长设置里做。
- **闯关地图**：只列出当前字库的组，标题用字库名，关卡编号在每个字库里从 1 开始。
- **解锁规则按字库分别计算**：每个字库的第 1 组总是开放；第 k 组要求第 k−1 组有 ≥ 8 个字的等级 ≥ 1；`unlockAll` 依然有效。

```js
function unlocked(lib, gi) {
  if (state.settings.unlockAll || gi === 0) return true;
  return lib.groups[gi - 1].chars.filter((x) => peek(x.c).l >= 1).length >= 8;
}
```

- **关卡页**：按 `lib.profile.games` 的顺序显示玩法按钮。如果这一组有图的字少于 4 个，就隐藏「看图找字」（见 Step 6）。

### Step 5 · 今日练习：复习全局，新字按当前字库

- **复习**：从**所有字库**里挑已经到期的字。以前字库里学过的字也要继续复习，不能因为换了字库就不管了。
- **新字**：从当前字库里、已解锁的组中，按顺序挑还没学过的字。每天引入的新字数量有上限（家长设置的 1–10 个，默认取字库 `profile.dailyNew`：3–4岁、4–5岁 3 个，5–6岁、6–7岁 5 个）。上限**按字库分别计数**，家长换了字库，当天就能学新字库的字。新字不会被复习挤掉：每次今日练习 = 今天剩下的新字 + 最多 10 个到期复习的字。

```js
function todayKey() { return new Date().toLocaleDateString('en-CA'); } // YYYY-MM-DD, local time
function newAllowanceToday() {
  if (state.newLog.day !== todayKey()) state.newLog = { day: todayKey(), byLib: {} };
  return Math.max(0, dailyNewLimit() - (state.newLog.byLib[currentLib().id] || 0));
}
// When the learn cards for fresh characters open in daily practice:
state.newLog.byLib[currentLib().id] = (state.newLog.byLib[currentLib().id] || 0) + fresh.length; save();
```

- 当前字库的字都学完了：新字自动从下一个字库里取，同时在首页显示一次提示「这个字库学完啦，家长可以换下一个字库」（新增 `ui.libraryDone`）。
- 在关卡页里主动点「学新字」**不受**每日上限限制。这是家长或孩子自己选的，也不计入 `newLog`。

> 时长上限（10 或 15 分钟）会在当前这一局结束后生效，剩下的时间孩子可以去闯关页玩游戏。

### Step 6 · 没有图的字

5–6岁、6–7岁字库的 `pic` 都是 `null`。各处的处理方式：

| 位置 | 有图 | 没图 |
|---|---|---|
| 学新字卡片左侧 | 大号 emoji | 大号例词，目标字用强调色 |
| 看图找字 | 正常 | 这一组有图的字少于 4 个时，隐藏这个玩法 |
| 看图找字的干扰项 | 排除和答案同图的字 | 排除 `pic` 为 `null` 的字 |
| 翻牌配对的「图卡」 | emoji | **听音卡**：牌面显示 🔊 和例词，例词里的目标字换成 `○`（如「○了」）；翻开时朗读例词 |
| 今日练习的混合出题 | 听音或看图 | 听音或选字填词 |

判断方法：`const hasPic = (c) => !!CHAR.get(c).pic;`

### Step 7 · 新玩法：选字填词（`fill`）

适合 5 岁以上，用来练虚词和抽象字。直接复用 `renderQuiz`，加一个 `mode: 'fill'`：

- **题面**：例词里的目标字换成一个小田字格空位，例如「好 □」，下面放一个小喇叭。出题时自动朗读例词。
- **选项**：4 个字，干扰项的挑法和听音找字一样（排除同音字）。还要加一条：把干扰项填进空位后，如果刚好组成字库里另一个字的例词，就排除它，避免出现两个都对的选项。

```js
function fillsAnotherWord(target, candidate) {
  const filled = CHAR.get(target).w.replace(target, candidate);
  return [...CHAR.values()].some((x) => x.w === filled);
}
```

- **反馈**：和其他玩法一样，用动画、星星和 `grade()`。答对后空位填上正确的字，再朗读一遍整个词。

需要新增的界面文字：

```json
"fill": "选字填词",
"fillHint": "哪个字能填进去？"
```

### Step 8 · 朗读模板跟着字库走

在 `ui` 里分两套模板：

```json
"sayCharWordOf": "{c}，{w}的{c}",
"sayCharCharWord": "{c}，{w}",
"promptWordOf": "找一找，{w}的{c}",
"promptCharWord": "找一找：{w}，{c}",
"thisIsWordOf": "这是{w}的{c}",
"thisIsCharWord": "这是{c}，{w}"
```

代码按**字所在的字库**来选模板，而不是按当前选中的字库。这样复习以前的字时，读法和当初学的时候一致。

```js
function speechStyle(c) { return LIBS[CHAR.get(c).lib].profile.speech; } // 'wordOf' | 'charWord'
function tpl(base, c) { return UI[base + (speechStyle(c) === 'wordOf' ? 'WordOf' : 'CharWord')]; }
// sayChar(c): speak(fmt(tpl('sayChar', c), { c, w: CHAR.get(c).w }))
```

### Step 9 · 拼音开关

- 学新字卡片：`settings.showPinyin` 为 false 时隐藏拼音那一行。
- 其他玩法本来就不显示拼音，不用改。
- 字宝箱：长按某个字时，可以临时显示它的拼音，方便家长核对（可选）。

### Step 10 · 字宝箱按字库分页

- 顶部显示总进度：「一共认识 N 个字 / 1000」（新增 `ui.boxTotal`）。
- 下面每个字库一个标签页，默认打开当前字库。每页内容和 v1 一样：按组排列，按熟练度着色。
- 每个标签上显示「已认识 n / m」。

### Step 11 · 发布

1. 运行 `python tools/build_charsets.py`，确认生成了 `data/charsets.json`。
2. `sw.js`：确认 `CORE` 里有 `./data/charsets.json`，`CACHE` 已经改成 `hanzi-garden-v2`。
3. 提交并推送到 GitHub，等 Pages 部署完成。
4. **不需要重新打包商店版**。商店版加载的就是 GitHub Pages 的网址，只要没改 `manifest.webmanifest` 里的名字和图标，就不用重新提交。

---

## 4. 测试清单

- [ ] 旧版的进度（星星、字宝箱颜色）在新版里还在
- [ ] 家长设置里切换 4 个字库，首页标签、地图、关卡都跟着变
- [ ] 切换字库后，时长和拼音开关变成这个字库的默认值，之后还能手动改
- [ ] 每个字库的第 1 组都是开放的；解锁规则在各个字库里分别计算
- [ ] 今日练习：同一天第二次打开时不再引入新字（3–4岁字库，默认每天 3 个）
- [ ] 换字库后，今日练习当天就出新字库的新字
- [ ] 今日练习：会复习以前字库里到期的字
- [ ] 5–6岁字库：学字卡显示大号例词；翻牌出现听音卡；看不到「看图找字」
- [ ] 选字填词：答对后空位填上字并朗读整个词；没有两个都对的选项
- [ ] 朗读：「木，木头的木」和「了，好了」两种模板各自用对
- [ ] 拼音开关生效
- [ ] 断网后仍能打开（Service Worker 缓存了 `charsets.json`）
- [ ] 手机竖屏（390px 宽）和 Windows 触屏上布局正常

---

## 5. 建议的提交顺序

1. `data: add 1000-character age libraries and build script`：新增 `tools/`、`data/`、`CHARSETS.md`
2. `feat: load charsets from data file`：Step 1 和 Step 2
3. `feat: parent picks library; map and groups follow current library`：Step 3 和 Step 4
4. `feat: daily practice uses global review and per-library daily new limit`：Step 5
5. `feat: support characters without pictures`：Step 6
6. `feat: add fill-in-the-word game`：Step 7
7. `feat: per-library speech templates and pinyin toggle`：Step 8 和 Step 9
8. `feat: treasure box tabs per library`：Step 10
9. `chore: bump service worker cache to v2`：Step 11

---

## 6. 字库的选字思路

| 字库 | 字数 | 思路 |
|---|---|---|
| 3–4岁 | 150 | 能用图画出来的具体字。v1 的 100 字，加上食物、更多动物、房子和路、户外、游戏动作 5 组 |
| 4–5岁 | 150 | 生活场景里的字：家人、身体、穿戴、吃饭、动作、四季、时间、方位、形容、学校、出门、游戏、心情。大部分仍然有图 |
| 5–6岁 | 300 | 最高频的虚词和代词（是、了、的、这、那、们、什么、吗、呢……），加上礼貌用语、数量词、学习、家里、好坏、因果连词。开始用例词代替图 |
| 6–7岁 | 400 | 上学前后常见的字：自然、动物、亲人、家务、文具、运动、声音、身体、厨房、地方、职业、时间、数学、品格、心情、童话、买东西，以及更多连词和副词 |

例词尽量用孩子熟悉的词，避开新闻里常见、孩子用不到的词。完整清单见 `CHARSETS.md`，建议家长通读一遍：

- 觉得不合适的字，可以在对应文件里直接替换，然后重新运行脚本；
- 发现读音有问题，就加到 `tools/pinyin_overrides.json` 里。

---

## 7. 以后可以做的

- 1000 字以后的字库，比如「7–8岁字库」，只要往 `lib56_67.txt` 里追加一段 `@age-7-8`，再在脚本的 `PROFILES` 里加一项。
- 大一点才开始用的孩子，可以加一个「测一测」：快速考一轮前面字库的字，认识的直接标记为已学。
- 可以给常用的虚词配一句例句（数据里加一个可选的 `s` 字段），朗读时读整句，比如「是：这是我的小猫」。
