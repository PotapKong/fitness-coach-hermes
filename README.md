# Fitness Coach for Hermes

Public MIT-licensed skill with a **private, local-first journal** for Hermes and other file-capable agents. Complements the official [`fitness-nutrition`](https://github.com/NousResearch/hermes-agent/tree/main/optional-skills/health/fitness-nutrition) skill (exercise guidance, wger, calculators); it does **not** bundle that skill. Its own food lookup uses USDA's free `DEMO_KEY` by default, with an optional `USDA_API_KEY`.

## Install in Hermes

```bash
hermes skills install official/health/fitness-nutrition
git clone https://github.com/PotapKong/fitness-coach-hermes.git
mkdir -p "$HOME/.hermes/skills/fitness-coach-hermes"
cp fitness-coach-hermes/{SKILL.md,README.md,EVIDENCE.md,VISUAL.md,LICENSE,coach.py,food_lookup.py} "$HOME/.hermes/skills/fitness-coach-hermes/"
# In Telegram start a new session or use /reload-skills after installing.
```

## Install in another agent

This repository uses portable Agent Skills layout: `SKILL.md` at the skill root and Python scripts beside it. Clone the public repository, then copy the **whole package** (not only `SKILL.md`) into your agent's skill directory. For runtimes that use `~/.codex/skills/` or `~/.claude/skills/`, place a `fitness-coach-hermes/` directory there and reload skills; consult that agent's own documentation for its exact path. Only the Hermes path above is exercised here. Set `SKILL_DIR` to that copied directory and `COACH_DATA_DIR` to a *separate local private data directory per person*. If an agent has no filesystem tool or no Telegram attachment capability, it can read the instructions but cannot execute the logger or deliver PNGs. Do not copy health logs, sessions or Telegram tokens between agents.

Python 3.10+ and Pillow for legacy local PNG rendering. In the cloned repo: `uv venv .venv && uv pip install --python .venv/bin/python pillow && . .venv/bin/activate` (or use any isolated environment with Pillow before calling `python3`). Install a Cyrillic-capable TTF font. The renderer searches common Linux/macOS/Windows paths; if none works, set `COACH_FONT_PATH` to a TTF file. Logging, food lookup and text reports use Python stdlib. No bot token or GitHub secret is needed. The commands below write **synthetic demonstration data only** to a fresh temporary private directory; do not run them against your real journal:

```bash
export COACH_DATA_DIR="$(mktemp -d)"  # demo only; do not mix with real data
export SKILL_DIR="$HOME/.hermes/skills/fitness-coach-hermes"
python3 "$SKILL_DIR/food_lookup.py" 'raw egg'  # inspect matching item, kcal unit, FDC ID and portion
python3 "$SKILL_DIR/coach.py" target --kcal 2100 --weekly-avg-min 2000 --weekly-avg-max 2200 --confirmed-by-user  # synthetic example; owner chooses
python3 "$SKILL_DIR/coach.py" meal --name "Example lunch" --kcal 620 --protein 32 --fat 20 --carbs 70 --source user
python3 "$SKILL_DIR/coach.py" food --fdc-id 171287 --grams 120  # only after confirming the food and portion
python3 "$SKILL_DIR/coach.py" workout --name "Example walk" --minutes 40
python3 "$SKILL_DIR/coach.py" workout --name "Example squat" --minutes 25 --sets 3 --reps 8 --load-kg 40
python3 "$SKILL_DIR/coach.py" weight --kg 80.5
python3 "$SKILL_DIR/coach.py" report
python3 "$SKILL_DIR/coach.py" trends --days 28
python3 "$SKILL_DIR/coach.py" snapshot --scope entry    # just after a new entry
python3 "$SKILL_DIR/coach.py" snapshot --scope day      # day plus week-to-date brief
python3 "$SKILL_DIR/coach.py" close-day --confirmed-by-user  # only after confirming a complete food log
python3 "$SKILL_DIR/coach.py" snapshot --scope week     # ISO Monday–Sunday
python3 "$SKILL_DIR/coach.py" card --view nutrition --output "$COACH_DATA_DIR/week.png"
python3 "$SKILL_DIR/coach.py" card --view activity --output "$COACH_DATA_DIR/activity.png"
python3 "$SKILL_DIR/coach.py" card --view micros --output "$COACH_DATA_DIR/micros.png"
python3 "$SKILL_DIR/coach.py" card --view micro-trend --nutrient iron_mg --output "$COACH_DATA_DIR/iron.png"
```

For actual use, set `COACH_DATA_DIR` to a private path outside the repository (for example `$HOME/.local/share/fitness-coach-hermes`) and obtain the owner's consent before storing anything. The target, lunch and weight above are **synthetic examples**, not a prescription or the owner's data. Set a target only after the user explicitly chooses it. A food photo does not establish exact calories. Use weighed portions or packaging/USDA entries; label uncertain estimates.

Important upstream caveat: the official `nutrition_search.py` currently maps nutrients by name and can output kJ as kcal when both Energy units occur (USDA FDC 171287: 599 kJ vs 143 kcal per 100 g). Use this repository's `food_lookup.py`, which filters explicitly for `unitName=kcal`; a missing kcal value remains null.

## Telegram

In a conversation with the agent: ask «Покажи отчёт за неделю и отправь карточку сюда». The agent runs `report` + `card`, inspects the result and returns an image attachment using `MEDIA:/absolute/path/week.png` to the current chat. It does not need a separate bot when Hermes Telegram gateway is already connected. Other agents need their own authenticated Telegram send/attachment route. Cards show logged calories, activity, available micronutrients and optional micronutrient history; `trends` emits dated JSON for longer comparison. No automatic sends, reminders or public sharing.

## Visuals and AI rendering

Three distinct **synthetic** GPT Image design references are included; no user's health data was used. They demonstrate card hierarchy, not an automatically generated or clinically validated report. See [entry receipt](examples/on-entry.webp), [day close](examples/day-close.webp), and [weekly review](examples/weekly-review.webp). The card agent must use `snapshot` plus explicit visual QA to make a new report; the images are not reusable numeric templates.

The built-in PNG is a deterministic data chart, not a diet-quality score. [VISUAL.md](VISUAL.md) defines three distinct AI-rendered card jobs (on-entry/day-end/week-end), exact-value QA and neutral/teal/amber color semantics. The CLI evaluates **recorded weekly-average energy** against a user-provided range only when all seven food days were owner-confirmed complete and none was photo-estimated. This is not a score of nutritional quality; without those conditions, use neutral colors and show coverage. Private health entries may be sent to an external image provider **only after separate informed consent**; otherwise render locally. Generated labels/bars are never the source of truth. For scheduled end-of-day/week delivery, configure the agent's own scheduler **after** agreeing on local timezone, times and destination; the skill does not create cron jobs automatically.

## Privacy / limitations

- `private-data/`, `*.png`, `.env` and caches are gitignored. Data outside the repo is preferred. Logs are health-adjacent personal information; avoid putting them in GitHub even if the repo is private.
- Journal and new PNG cards are atomically written with owner-only file permissions (0600); this is not encrypted storage. Keep the parent folder private and back it up securely if needed.
- Journal writes use an exclusive local lock; a stale `.journal.lock` after a crash blocks new writes until the owner verifies no writer is active and removes that file. If several agents share a journal, pass a stable `--event-id` for each incoming message to prevent retry duplicates. Never upload real health records to GitHub, even though this code repository is public.
- Reports count **logged meals**, not all food eaten. A blank day means no records, not fasting. The goal is user-supplied, not medically assigned.
- If the user reports symptoms, a medical condition, an eating disorder, pregnancy, or significant pain, refer to a qualified professional rather than prescribing a regimen.
- Primary sources and comparisons with other open agent skills are in [EVIDENCE.md](EVIDENCE.md). Their ranges describe populations, not an automatic personal plan.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Upstream source: NousResearch/hermes-agent, `optional-skills/health/fitness-nutrition` (checked at `c419cf7c864ac0ee511dbd9f7091a8bba0b567ee`). This project links to that MIT-licensed skill rather than copying it, and has no implied upstream endorsement. This project's code and documentation are MIT-licensed; see [LICENSE](LICENSE).
