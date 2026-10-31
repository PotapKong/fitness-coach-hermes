# Fitness Coach for Hermes

Private, local-first fitness journal and weekly progress card for Hermes agents. Complements the official [`fitness-nutrition`](https://github.com/NousResearch/hermes-agent/tree/main/optional-skills/health/fitness-nutrition) skill (exercise guidance, wger, calculators); it does **not** bundle that skill. Its own food lookup uses USDA's free `DEMO_KEY` by default, with an optional `USDA_API_KEY`.

## Install in Hermes

```bash
hermes skills install official/health/fitness-nutrition
gh repo clone PotapKong/fitness-coach-hermes
mkdir -p "$HOME/.hermes/skills/fitness-coach-hermes"
cp fitness-coach-hermes/{SKILL.md,README.md,coach.py,food_lookup.py} "$HOME/.hermes/skills/fitness-coach-hermes/"
# In Telegram start a new session or use /reload-skills after installing.
```

## Install in another agent

This repository uses portable Agent Skills layout: `SKILL.md` at the skill root and Python scripts beside it. On a target machine, authenticate to the owner's **private** GitHub repo with its own authorized GitHub account, then clone and copy the **whole package** (not only `SKILL.md`) into that agent's skill directory. For example, when the target runtime uses `~/.codex/skills/` or `~/.claude/skills/`, put `fitness-coach-hermes/` there and reload its skills. Exact skill paths and reload commands depend on that runtime; only the Hermes path above is exercised here. Set `SKILL_DIR` to that copied directory and `COACH_DATA_DIR` to a *separate local private data directory per person*. If an agent has no filesystem tool or no Telegram attachment capability, it can read the instructions but cannot execute the logger or deliver PNGs. Do not copy health logs, sessions or Telegram tokens between agents. A GitHub URL alone does **not** grant private-repo access. For public installation, the owner would need to explicitly publish a code-only version.

Python 3.10+ and Pillow for PNG rendering (`uv venv && uv pip install pillow`, or install in an isolated environment). On Linux, a DejaVu Sans font is needed for Cyrillic PNG text. Logging, food lookup and text reports use Python stdlib. No bot token or GitHub secret is needed. Use a private data directory outside the cloned repo:

```bash
export COACH_DATA_DIR="$HOME/.local/share/fitness-coach-hermes"
export SKILL_DIR="$HOME/.hermes/skills/fitness-coach-hermes"
python3 "$SKILL_DIR/food_lookup.py" 'raw egg'  # inspect matching item, kcal unit, FDC ID and portion
python3 "$SKILL_DIR/coach.py" target --kcal 2100              # example only; user chooses target
python3 "$SKILL_DIR/coach.py" meal --name "Example lunch" --kcal 620 --protein 32 --fat 20 --carbs 70 --source user
python3 "$SKILL_DIR/coach.py" food --fdc-id 171287 --grams 120  # only after confirming the food and portion
python3 "$SKILL_DIR/coach.py" workout --name "Example walk" --minutes 40
python3 "$SKILL_DIR/coach.py" workout --name "Example squat" --minutes 25 --sets 3 --reps 8 --load-kg 40
python3 "$SKILL_DIR/coach.py" weight --kg 80.5
python3 "$SKILL_DIR/coach.py" report
python3 "$SKILL_DIR/coach.py" trends --days 28
python3 "$SKILL_DIR/coach.py" card --view nutrition --output "$COACH_DATA_DIR/week.png"
python3 "$SKILL_DIR/coach.py" card --view activity --output "$COACH_DATA_DIR/activity.png"
python3 "$SKILL_DIR/coach.py" card --view micros --output "$COACH_DATA_DIR/micros.png"
python3 "$SKILL_DIR/coach.py" card --view micro-trend --nutrient iron_mg --output "$COACH_DATA_DIR/iron.png"
```

The target, example lunch and weight above are **synthetic examples**, not a prescription or the owner's data. Set a target only after the user explicitly chooses it. A food photo does not establish exact calories. Use weighed portions or packaging/USDA entries; label uncertain estimates.

Important upstream caveat: the official `nutrition_search.py` currently maps nutrients by name and can output kJ as kcal when both Energy units occur (USDA FDC 171287: 599 kJ vs 143 kcal per 100 g). Use this repository's `food_lookup.py`, which filters explicitly for `unitName=kcal`; a missing kcal value remains null.

## Telegram

In a conversation with the agent: ask «Покажи отчёт за неделю и отправь карточку сюда». The agent runs `report` + `card`, inspects the result and returns an image attachment using `MEDIA:/absolute/path/week.png` to the current chat. It does not need a separate bot when Hermes Telegram gateway is already connected. Other agents need their own authenticated Telegram send/attachment route. Cards show logged calories, activity, available micronutrients and optional micronutrient history; `trends` emits dated JSON for longer comparison. No automatic sends, reminders or public sharing.

## Privacy / limitations

- `private-data/`, `*.png`, `.env` and caches are gitignored. Data outside the repo is preferred. Logs are health-adjacent personal information; avoid putting them in GitHub even if the repo is private.
- Journal and new PNG cards are atomically written with owner-only file permissions (0600); this is not encrypted storage. Keep the parent folder private and back it up securely if needed.
- Use one writer per person's journal: concurrent agents editing the same JSON file are not coordinated and can overwrite each other's updates. A private repo does **not** make uploaded health records safe; keep them out of GitHub.
- Reports count **logged meals**, not all food eaten. A blank day means no records, not fasting. The goal is user-supplied, not medically assigned.
- If the user reports symptoms, a medical condition, an eating disorder, pregnancy, or significant pain, refer to a qualified professional rather than prescribing a regimen.
- Primary sources and comparisons with other open agent skills are in [EVIDENCE.md](EVIDENCE.md). Their ranges describe populations, not an automatic personal plan.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Upstream source: NousResearch/hermes-agent, `optional-skills/health/fitness-nutrition` (checked at `c419cf7c864ac0ee511dbd9f7091a8bba0b567ee`). This project links to that MIT-licensed skill rather than copying it, and has no implied upstream endorsement. This repository is private and does not grant a public reuse license.
