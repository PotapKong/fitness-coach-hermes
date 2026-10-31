---
name: fitness-coach-hermes
description: Use when tracking a person's workouts, meals, calories, weight and weekly progress with private local data, or sending a verified progress card to Telegram.
version: 0.1.0
metadata:
  hermes:
    tags: [fitness, nutrition, calorie-tracking, telegram, progress]
---

# Fitness Coach for Hermes

This is a **local-first logging/delivery companion** to the official Hermes `fitness-nutrition` skill (`official/health/fitness-nutrition`). Install both packages separately. The upstream skill provides exercise guidance and offline TDEE calculators; this package provides a unit-checked USDA food lookup, records user-confirmed values and creates a legible weekly card. Never claim this companion itself diagnosed a condition or sent a message automatically.

## First-use safety and consent

- Ask whether the person wants persistent **local** fitness logs. Do not log health data until they consent. Use a private data directory outside git (`COACH_DATA_DIR`); never commit real logs, photos or measurements. Do not mix multiple people's data in one directory.
- Ask for a goal and limitations (including conditions, pain, pregnancy, history of disordered eating) before suggesting a training or calorie target. Refer clinical, eating-disorder or concerning symptoms to a qualified professional. No exercise through acute pain, and no extreme caloric deficits or automatic goals from a photo.
- Daily calories from a food photo are an **uncertain estimate**, especially for portions, oils and sauces. Ask for package labels/weights or the user's confirmation. State source and uncertainty; do not fabricate exact macros. USDA entries are per 100 g; scale by a confirmed portion using a calculator tool, not mental arithmetic.
- Keep medical and personal details out of the Telegram card. Send only to the clearly specified chat/topic when the user requests delivery, never to a group or third party by default.

## Workflow

Resolve `SKILL_DIR` to the directory containing **this** SKILL.md (not the current working directory), then invoke `python3 "$SKILL_DIR/coach.py"`. Set `COACH_DATA_DIR` to a per-person private directory outside the repository. On this host the installed file is under `~/.hermes/skills/fitness-coach-hermes/`; another machine may use a different path.

1. For exercise names and TDEE, load `fitness-nutrition` if installed (`hermes skills install official/health/fitness-nutrition` after reviewing its scope). Do not mistake its BMI/TDEE estimate for a diagnosis or a measured energy expenditure. **Do not use upstream `nutrition_search.py` for calories:** it selects nutrients by name only and can mistake kJ for kcal (e.g. USDA FDC 171287, 599 kJ vs 143 kcal). For food data run `python3 "$SKILL_DIR/food_lookup.py" "food name"`, which matches energy by kcal unit. It uses `DEMO_KEY` unless `USDA_API_KEY` is set. Never convert a null nutrient to zero.
2. Ask the user to confirm portions/macros before logging. Log a meal with an explicit source:
   `python3 "$SKILL_DIR/coach.py" --data-dir "$COACH_DATA_DIR" meal --date YYYY-MM-DD --name "..." --kcal N --protein N --fat N --carbs N --source label|usda|user|photo-estimate`
   For a USDA result, compute values for the actual weighed portion; include the FDC identifier and serving in the meal name if possible.
3. Log exercise via `workout --name "..." --minutes N`, weight via `weight --kg N` and a user-approved goal via `target --kcal N`. The tool appends entries; if a correction is needed, do not append a duplicate—edit the exact record with the owner's consent or implement an audited correction command.
4. For Telegram text run `report --date YYYY-MM-DD`; for a card run `card --date YYYY-MM-DD --output /absolute/private/path/card.png`. Inspect both; the report is based only on entered data and missing meals must not be treated as zero intake.
5. When the user asks for a Telegram update, send the **verified card** as a native image to the exact chat/thread with a short text summary. In a direct Hermes reply, `MEDIA:/absolute/private/path/card.png` sends a standalone image. For a different destination use a supported, verified Hermes send route and read it back. Do not assume the CLI `MEDIA:` plus body becomes a photo caption.
6. Never silently schedule reminders or send the health history to another service. No repository push should contain `private-data/` or generated cards.

## Delivery and validation

Run `python3 -m unittest discover -s tests -v`; smoke test `report` and `card` in a temporary data directory. Open the card and check mobile legibility; totals must match the report. Live Telegram delivery is verified only after the user asks for a specific send and the exact message is read back. See `README.md` for setup and examples.
