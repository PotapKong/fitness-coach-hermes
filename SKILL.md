---
name: fitness-coach-hermes
description: Use when tracking a person's workouts, meals, calories, weight and weekly progress with private local data, or sending a verified progress card to Telegram.
version: 0.2.0
metadata:
  hermes:
    tags: [fitness, nutrition, calorie-tracking, telegram, progress]
---

# Fitness Coach for Hermes

This is a **portable Agent Skill** and local-first logging/delivery companion to the official Hermes `fitness-nutrition` skill (`official/health/fitness-nutrition`). Install both on Hermes; on other agents this package works independently for logging and USDA lookup. Upstream provides exercise guidance and offline TDEE calculators; this package provides a unit-checked USDA food lookup, records confirmed values and creates weekly cards. Never claim this companion diagnosed a condition or sent a message automatically.

## First-use safety and consent

- Ask whether the person wants persistent **local** fitness logs. Do not log health data until they consent. Use a private data directory outside git (`COACH_DATA_DIR`); never commit real logs, photos or measurements. Do not mix multiple people's data in one directory.
- Ask for a goal and limitations (including conditions, pain, pregnancy, history of disordered eating) before suggesting a training or calorie target. Refer clinical, eating-disorder or concerning symptoms to a qualified professional. No exercise through acute pain, and no extreme caloric deficits or automatic goals from a photo.
- Daily calories from a food photo are an **uncertain estimate**, especially for portions, oils and sauces. Ask for package labels/weights or the user's confirmation. State source and uncertainty; do not fabricate exact macros. USDA entries are per 100 g; scale by a confirmed portion using a calculator tool, not mental arithmetic.
- Keep medical and personal details out of the Telegram card. Send only to the clearly specified chat/topic when the user requests delivery, never to a group or third party by default.
- Use population guidance only with context, not as a personal prescription; do not set a default deficit, supplement dose or forced training progression. A micronutrient chart cannot diagnose deficiency. See `EVIDENCE.md` for primary sources, scope and compared skills.

## Workflow

Resolve `SKILL_DIR` to the directory containing **this** SKILL.md (not the current working directory), then invoke `python3 "$SKILL_DIR/coach.py"`. Set `COACH_DATA_DIR` to a per-person private directory outside the repository. On this host the installed file is under `~/.hermes/skills/fitness-coach-hermes/`; another machine may use a different path. This repository is **private**: other agents need explicit GitHub access or a copy from the owner, not just its URL. Use a single writer per journal; parallel agents can overwrite updates.

1. For exercise names and TDEE, load `fitness-nutrition` if installed (`hermes skills install official/health/fitness-nutrition` after reviewing its scope). Do not mistake its BMI/TDEE estimate for a diagnosis or a measured energy expenditure. **Do not use upstream `nutrition_search.py` for calories:** it selects nutrients by name only and can mistake kJ for kcal (e.g. USDA FDC 171287, 599 kJ vs 143 kcal). For food data run `python3 "$SKILL_DIR/food_lookup.py" "food name"`, which matches energy by kcal unit. It uses `DEMO_KEY` unless `USDA_API_KEY` is set. Never convert a null nutrient to zero.
2. Ask the user to confirm portions/macros before logging. Log a meal with an explicit source:
   `python3 "$SKILL_DIR/coach.py" --data-dir "$COACH_DATA_DIR" meal --date YYYY-MM-DD --name "..." --kcal N --protein N --fat N --carbs N --source label|usda|user|photo-estimate`
   For a USDA result, compute values for the actual weighed portion; include the FDC identifier and serving in the meal name if possible.
3. Log a weighed USDA food with `food --fdc-id ID --grams G` only after matching the exact product/preparation; this records units, portion, macros and available micronutrients. For a manual estimate use `meal` and mark the source. Missing values remain unknown (`null`), not zero. Do not equate one database entry with a whole dish or treat `0` on an incomplete log as actual intake.
4. Log exercise via `workout --name "..." --minutes N` (optionally all of `--sets N --reps N --load-kg N`), weight via `weight --kg N` and a user-approved goal via `target --kcal N`. The tool appends entries; if a correction is needed, do not append a duplicate—edit the exact record with the owner's consent or implement an audited correction command.
5. For Telegram text run `report --date YYYY-MM-DD`; for 7/14/28/90-day machine-readable dynamics run `trends --date YYYY-MM-DD --days N`. For cards run `card --date YYYY-MM-DD --view nutrition|activity|micros|micro-trend --nutrient iron_mg --output /absolute/private/path/card.png`. Inspect rendered numbers, legends, missing days and current user's privacy. `micros` shows recorded amounts only; `micro-trend` scales bars to the *maximum recorded*, not to an RDA. Never diagnose a deficiency from a journal or suggest supplements/doses from these charts.
6. When the user asks for a Telegram update, send the **verified card** as a native image to the exact chat/thread with a short text summary. In a direct Hermes reply, `MEDIA:/absolute/private/path/card.png` sends a standalone image. For other agents use their native attachment tool. For a different destination use a supported, verified route and read it back. Do not assume `MEDIA:` plus body becomes a photo caption.
7. Never silently schedule reminders or send the health history to another service. No repository push should contain `private-data/` or generated cards.

## Delivery and validation

Run `python3 -m unittest discover -s tests -v`; smoke test `report` and `card` in a temporary data directory. Open the card and check mobile legibility; totals must match the report. Live Telegram delivery is verified only after the user asks for a specific send and the exact message is read back. See `README.md` for setup and examples.
