# Fitness Coach for Hermes

Public MIT-licensed skill with a **private, local-first journal** for Hermes and other file-capable agents. Complements the official [`fitness-nutrition`](https://github.com/NousResearch/hermes-agent/tree/main/optional-skills/health/fitness-nutrition) skill (exercise guidance, wger, calculators); it does **not** bundle that skill. Its own food lookup uses USDA's free `DEMO_KEY` by default, with an optional `USDA_API_KEY`.

## Install in Hermes

```bash
hermes skills install official/health/fitness-nutrition  # optional complement
git clone https://github.com/PotapKong/fitness-coach-hermes.git
python3 fitness-coach-hermes/update_skill.py --check
python3 fitness-coach-hermes/update_skill.py --apply
# In Telegram start a new session or use /reload-skills after installing.
```

Read [UPDATES.md](UPDATES.md) for an opt-in daily repo-update cron, rollback, supply-chain risk and verification. The update cron is separate from all health-message scheduling; installation itself does not authorize meal ideas, reminders or delivery.

## Install in another agent

This repository uses portable Agent Skills layout: `SKILL.md` at the skill root and Python scripts beside it. Clone the public repository, then copy the **whole package** (not only `SKILL.md`) into your agent's skill directory. For runtimes that use `~/.codex/skills/` or `~/.claude/skills/`, place a `fitness-coach-hermes/` directory there and reload skills; consult that agent's own documentation for its exact path. Only the Hermes path and updater cron above are exercised here. Set `SKILL_DIR` to that copied directory and `COACH_DATA_DIR` to a *separate local private data directory per person*. If an agent has no filesystem tool or no Telegram attachment capability, it can read the instructions but cannot execute the logger or deliver PNGs. Do not copy health logs, sessions or Telegram tokens between agents.

Python 3.10+ and Pillow for legacy local PNG rendering. In the cloned repo: `uv venv .venv && uv pip install --python .venv/bin/python pillow && . .venv/bin/activate` (or use any isolated environment with Pillow before calling `python3`). Install a Cyrillic-capable TTF font. The renderer searches common Linux/macOS/Windows paths; if none works, set `COACH_FONT_PATH` to a TTF file. Logging, food lookup and text reports use Python stdlib. No bot token or GitHub secret is needed. The commands below write **synthetic demonstration data only** to a fresh temporary private directory; do not run them against your real journal:

```bash
export COACH_DATA_DIR="$(mktemp -d)"  # demo only; do not mix with real data
export SKILL_DIR="$HOME/.hermes/skills/fitness-coach-hermes"
python3 "$SKILL_DIR/food_lookup.py" 'raw egg'  # inspect matching item, kcal unit, FDC ID and portion
python3 "$SKILL_DIR/coach.py" target --kcal 2100 --weekly-avg-min 2000 --weekly-avg-max 2200 --confirmed-by-user  # synthetic example; owner chooses
python3 "$SKILL_DIR/coach.py" visual-profile --style bold-athletic --food-scene playful --confirmed-by-user  # synthetic demo only
python3 "$SKILL_DIR/coach.py" meal --name "Example lunch" --kcal 620 --protein 32 --fat 20 --carbs 70 --source user --event-id demo:lunch:1
python3 "$SKILL_DIR/coach.py" food --fdc-id 171287 --grams 120  # only after confirming the food and portion
python3 "$SKILL_DIR/coach.py" workout --name "Example walk" --minutes 40
python3 "$SKILL_DIR/coach.py" workout --name "Example squat" --minutes 25 --sets 3 --reps 8 --load-kg 40
python3 "$SKILL_DIR/coach.py" weight --kg 80.5
python3 "$SKILL_DIR/coach.py" report
python3 "$SKILL_DIR/coach.py" trends --days 28
python3 "$SKILL_DIR/coach.py" snapshot --scope entry --event-id demo:lunch:1    # exact entry, not last event
python3 "$SKILL_DIR/coach.py" snapshot --scope day      # day plus week-to-date brief
python3 "$SKILL_DIR/coach.py" close-day --confirmed-by-user  # only after confirming a complete food log
python3 "$SKILL_DIR/coach.py" snapshot --scope week     # ISO Monday–Sunday
python3 "$SKILL_DIR/coach.py" card --view nutrition --output "$COACH_DATA_DIR/week.png"
python3 "$SKILL_DIR/coach.py" card --view activity --output "$COACH_DATA_DIR/activity.png"
python3 "$SKILL_DIR/coach.py" card --view micros --output "$COACH_DATA_DIR/micros.png"
python3 "$SKILL_DIR/coach.py" card --view micro-trend --nutrient iron_mg --output "$COACH_DATA_DIR/iron.png"
```

For actual use, set `COACH_DATA_DIR` to a private path outside the repository (for example `$HOME/.local/share/fitness-coach-hermes`) and obtain the owner's consent before storing anything. The target, lunch and weight above are **synthetic examples**, not a prescription or the owner's data. Set a target only after the user explicitly chooses it. A food photo does not establish exact calories. Use weighed portions or packaging/USDA entries; label uncertain estimates.

## Long-term private history (not chat context)

`journal.json` in `COACH_DATA_DIR` is the durable source of truth. Every write also mirrors the full journal and indexed entries into owner-only `journal.sqlite3` in that **same private per-person directory**; corrections and completed-day markers are indexed. This is a local database, not Hermes conversation memory or a cloud sync. Upgrading a pre-database journal is non-destructive: the first write creates SQLite; to build SQLite **without modifying the old JSON**, run `python3 "$SKILL_DIR/history_db.py" --data-dir "$COACH_DATA_DIR" sync`. If a database index update fails, keep the JSON and retry `sync`; if SQLite is corrupt, first get owner approval, then run `python3 "$SKILL_DIR/history_db.py" --data-dir "$COACH_DATA_DIR" repair --confirmed-by-user`. It quarantines the corrupt DB (does not delete it) and rebuilds from the JSON. Do not publish either file. Back up the private directory securely.

```bash
python3 "$SKILL_DIR/history_db.py" --data-dir "$COACH_DATA_DIR" history --from-date 2026-01-01 --limit 50 --offset 0
python3 "$SKILL_DIR/history_db.py" --data-dir "$COACH_DATA_DIR" progress --limit 12 --offset 0
python3 "$SKILL_DIR/history_db.py" --data-dir "$COACH_DATA_DIR" history --include-voided --limit 50
python3 "$SKILL_DIR/history_db.py" --data-dir "$COACH_DATA_DIR" corrections --limit 50
```

History queries page through **all years** and expose `has_more` and a verified total; they do not flood one chat with the whole journal. Monthly progress distinguishes confirmed-complete days with known energy from partial recorded totals, shows recorded activity and weight observations; it never fills missing days with zero or infers medical outcomes. The agent should query the database for the relevant period in each new session instead of storing private records in global memory.

Important upstream caveat: the official `nutrition_search.py` currently maps nutrients by name and can output kJ as kcal when both Energy units occur (USDA FDC 171287: 599 kJ vs 143 kcal per 100 g). Use this repository's `food_lookup.py`, which filters explicitly for `unitName=kcal`; a missing kcal value remains null.

## Telegram

In a conversation with the agent: ask «Покажи отчёт за неделю и отправь карточку сюда». The agent runs `report` + `card`, inspects the result and returns an image attachment using `MEDIA:/absolute/path/week.png` to the current chat. It does not need a separate bot when Hermes Telegram gateway is already connected. Other agents need their own authenticated Telegram send/attachment route. Cards show logged calories, activity, available micronutrients and optional micronutrient history; `trends` emits dated JSON for longer comparison. No automatic sends, reminders or public sharing **by default**. For independently approved morning ideas and missing-log reminders, follow [AUTOMATION.md](AUTOMATION.md); the package does not create cron jobs or transmit messages.

## Visuals and AI rendering

Two different families of **synthetic** GPT Image design references are included; no user's health data was used. The original neutral/editorial family is archived as [entry](examples/on-entry.webp), [day](examples/day-close.webp), [week](examples/weekly-review.webp); its **empty weekly plate is a rejected motif, not a pattern to copy**. The new bold-athletic family shows actual **synthetically logged** food names in [entry](examples/bold-on-entry.png), [day](examples/bold-day-close.png), and [week](examples/bold-weekly-review.png); four of 18 named meal entries appear in its weekly scene, marked “часть записей”. These show art direction, not an automatically generated or clinically validated report. The card agent must use `snapshot` plus explicit visual QA to make a new card; example numbers and foods are not reusable templates.

To individualize future cards, ask the owner to choose a visual style and food-scene mode, then run `visual-profile --style bold-athletic|high-energy|editorial|minimal|adaptive --food-scene literal|playful|abstract --confirmed-by-user`. `snapshot --scope entry|day|week` now provides the actual logged meal and workout labels, optional **confirmed** grams and the chosen visual preferences. Gender or weight does not determine the palette or food quantity. An empty plate is not used for unknown food; a bucket/mountain requires a playful opt-in, labelled metaphor, and named foods, never a size inferred from kcal. See [VISUAL.md](VISUAL.md).

The built-in PNG is a deterministic data chart, not a diet-quality score. [VISUAL.md](VISUAL.md) defines three distinct AI-rendered card jobs (on-entry/day-end/week-end), exact-value QA and neutral/teal/amber color semantics. The CLI evaluates **recorded weekly-average energy** against a user-provided range only when all seven food days were owner-confirmed complete and none was photo-estimated. This is not a score of nutritional quality; without those conditions, use neutral colors and show coverage. Private health entries may be sent to an external image provider **only after separate informed consent**; otherwise render locally. Generated labels/bars are never the source of truth. For scheduled end-of-day/week delivery, configure the agent's own scheduler **after** agreeing on local timezone, times and destination; the skill does not create cron jobs automatically.

## Audit, recipes and optional morning ideas

An [independent scoped review](AUDIT.md) scored the older revision 6.5/10 for local journaling. A subsequent independent review of public SHA `ece7df5a285ec6cd0bdda937f660c60b598de730` scored **8/10 for local journaling/reporting** and **3/10 for an autonomous nutrition/training coach** (29 tests). These are scoped historical scores, **not a new score for this revision**. It highlighted correction/edit absence, lack of real delivery and the code-update trust boundary. This revision adds a confirmed correction/void flow, conservative numeric ceilings and private consent/dedupe primitives, but **still has no verified delivery adapter or clinical standing**.

The current catalog has 88 source-linked recipe pages across 12 first-party domains (including [NHS Healthier Families](https://www.nhs.uk/healthier-families/recipes/)); it stores short editorial metadata, not full copyrighted methods/photos. Source preparation time is not always ready-to-eat time: passive chilling is labelled separately. `recipe_sources.py` stages candidates for manual review, never auto-imports. `ideas.py --profile /private/path/profile.json --date YYYY-MM-DD` selects a link and a cautious optional activity candidate from an explicitly confirmed, private `0600` profile. It does not generate a meal plan, determine whether a recipe is safe for an allergy, schedule delivery or read the journal. For restrictions or allergies it withholds automatic recipe suggestions. `automation_core.py` adds private subscription/dedupe state, but **does not transmit messages or create notification jobs**. See [AUTOMATION.md](AUTOMATION.md).

## Privacy / limitations

- `private-data/`, `*.png`, `.env` and caches are gitignored. Data outside the repo is preferred. Logs are health-adjacent personal information; avoid putting them in GitHub even if the repo is private.
- Journal and new PNG cards are atomically written with owner-only file permissions (0600); this is not encrypted storage. Keep the parent folder private and back it up securely if needed.
- Journal writes use an exclusive local lock; a stale `.journal.lock` after a crash blocks new writes until the owner verifies no writer is active and removes that file. If several agents share a journal, pass a stable `--event-id` for each incoming message to prevent retry duplicates. Never upload real health records to GitHub, even though this code repository is public.
- With explicit owner confirmation, `correct-entry --event-id ORIGINAL --correction-id UNIQUE --field kcal --value 450 --confirmed-by-user` updates one exact record, retains a private before/after audit trail and reopens the food day. Use `--value unknown` for uncertain optional nutrients; `void-entry` deactivates a wrong record before re-logging. Never use these commands to silently alter a person's journal.
- Reports count **logged meals**, not all food eaten. A blank day means no records, not fasting; food with unknown calories is `null`, not `0`. `trends` averages only owner-confirmed complete food days where every logged food has known calories. A printed subtotal on a partial day is explicitly marked partial. The goal is user-supplied, not medically assigned.
- If the user reports symptoms, a medical condition, an eating disorder, pregnancy, or significant pain, refer to a qualified professional rather than prescribing a regimen.
- Primary sources and comparisons with other open agent skills are in [EVIDENCE.md](EVIDENCE.md). Their ranges describe populations, not an automatic personal plan.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Upstream source: NousResearch/hermes-agent, `optional-skills/health/fitness-nutrition` (checked at `c419cf7c864ac0ee511dbd9f7091a8bba0b567ee`). This project links to that MIT-licensed skill rather than copying it, and has no implied upstream endorsement. This project's code and documentation are MIT-licensed; see [LICENSE](LICENSE).
