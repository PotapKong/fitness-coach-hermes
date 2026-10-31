# Optional morning ideas and missing-log reminders

Nothing in this skill sends messages or creates scheduled jobs by itself. `ideas.py` returns a **read-only local candidate** with a source URL; Hermes cron and the user's platform deliver messages only after separate, explicit opt-ins. The absence of a food/workout entry is unknown, not proof of missed eating, a skipped workout or a failed goal.

## Permission interview (per person, before creating any job)

- Ask independently: “Do you want a daily morning recipe/activity idea?” and “Do you want a gentle reminder if you haven't recorded food today?” Declining either leaves it off. Never infer opt-in from installation, prior one-off requests or prior journal entries.
- Confirm each local send time, IANA zone (e.g. `Europe/Berlin`, not merely “local”), quiet hours, maximum one send of each type per local date, delivery platform/chat/**topic**, and what counts as a no-log condition. User can pause or cancel at any time; pause/remove both the cron job and consent record. Never guess a recipient from a message envelope or send health details to a group by default.
- Ask privately and optionally for tastes, disliked foods, dietary exclusions, allergens, cooking time, kitchen equipment, budget and activity preferences. Ask about limitations, pain, pregnancy or medical concerns before exercise suggestions; avoid prescribing a plan if unknown or concerning. Store only agreed fields in a private `0600` profile outside the repository. Keep profile separate from log and avoid disclosing it to external image/recipe services.
- Do not auto-select supposedly allergen-safe dishes from short ingredient hints. `ideas.py` deliberately returns no recipe if allergies or dietary exclusions are set. If missing essential preferences, ask rather than inventing them.

## Local catalog and candidate

`recipes.json` is a source-linked, extensible library, not a calorie prescription or a full meal plan. Each item needs a unique ID, title, canonical source URL, verified prep/cook minutes, meal tags, short non-exhaustive ingredient hints and a review date. Longer passive time (overnight chia setting, marinating, cooling) belongs in `rest_minutes` or an explicit note, not under a misleading “10-minute ready” claim. To add entries, verify the first-party page, do not copy its whole method or photography, never infer allergy safety from hints, and test filtering. A menu preference, user budget or local food availability may require a different source. Editorial tags describe *usefulness* (`quick`, `make_ahead`, `portable`, `vegetable_forward`, `protein_featured`), not a medical goal, macro guarantee or “good/bad” food grade.

For a **synthetic demonstration only**, create a local private profile file outside the git checkout (never commit anyone's preferences). Example JSON:

```json
{
  "version": 1,
  "food": {
    "preferences_confirmed": true,
    "allergies": [],
    "dietary_exclusions": [],
    "max_minutes": 25,
    "meal": "breakfast",
    "disliked_ingredients": []
  },
  "activity": {
    "preferences_confirmed": true,
    "cleared_for_general_activity": true,
    "preferred_activities": ["walking"]
  }
}
```

This example is fictional. Do **not** set `cleared_for_general_activity` from inference; only after the owner has discussed limitations. Save as `0600` in a private directory; `python3 ideas.py --profile /private/path/profile.json --date YYYY-MM-DD` prints JSON. It does not read/send the journal and has no network access; the URL is only printed. Check the linked recipe's full ingredients and equipment before recommending. The picker rotates deterministically within the chosen meal/time filters, and will not generate an invented recipe if none match. For a morning idea, `max_minutes` bounds **prep + cook + passive waiting**; evening make-ahead candidates may exceed that ready-to-eat time, so display both `minutes` (active/clock time) and `ready_minutes` and tell the owner to prepare in advance. Optional `liked_recipe_ids`, `disliked_recipe_ids` and `preferred_tags` in the *user-confirmed* private profile tune selection; `--history /private/0600/offers.json` avoids recipes **actually delivered** in the preceding seven local days. Suggested is not cooked: add to offer history only after verified delivery, never infer liking from a click or a food log. Missing, `null`, or non-list allergies/exclusions cause a safe no-recommendation; explicit food exclusions also disable automatic recipe selection rather than claiming verified compatibility.

## Weekly discovery and preference loop

Once a week, after the owner explicitly opts into recurring **public web research** (independent of private notifications), discover a bounded batch of new recipe pages across first-party creators, dietitian publishers and regional sources. Search for variety by breakfast/lunch/dinner/snack, fast cooking vs make-ahead, affordable ingredients and visual appeal; do not favor only “low calorie” or branded supplements. Open each canonical page and verify title, prep/cook/overnight time, equipment, ingredients, accessible link and provenance. `python3 recipe_sources.py --allow-domain nhs.uk https://www.nhs.uk/healthier-families/recipes/eggs-paprika/` demonstrates **candidate staging only**. It deliberately does not import pages into the catalog. Human/agent editorial review deduplicates IDs/canonical URLs, checks rights and content quality, records `checked_on`, and updates the public catalog only after tests. Keep private tastes and user health data out of search queries and Git commits. Reject inaccessible/redirected pages, unsourced time claims and duplicates; if no credible sources this week, publish zero new entries instead of padding the count.

At week end, with separate permission to mention observed meals, run `python3 ideas.py --profile /private/0600/profile.json --weekly-feedback --journal /private/0600/journal.json --date YYYY-MM-DD`. It outputs names explicitly recorded in the preceding seven days and a neutral question: which of those tasted best, which to repeat/avoid? **Do not** claim a suggested recipe was cooked. If no meals were logged, skip the question; if a person answers, update only the preferences they explicitly chose. Never infer preferences from weight, macros or an unconfirmed journal. The picker uses confirmed likes/tags, excludes explicit dislikes, avoids recently delivered repeats and falls back gracefully when the eligible pool is small. No automatic external feedback collection is bundled.

## Delivery architecture for an opted-in agent

Use [Hermes cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) **only after** the user has approved the exact details; create distinct morning and reminder jobs. A scheduled agent must re-check the current subscription on each run, resolve today's date in the approved IANA time zone, respect quiet hours/DST and validate the saved route/topic. The morning job may render the candidate idea and a short gentle activity suggestion, or state that preferences are needed; never emit a nutrition target. The reminder job reads the current journal immediately before delivery: if today's food entry exists, do not remind; if there is no entry and consent is still active, ask gently “Если удобно, можно отметить, что сегодня было из еды. Нет записи — это просто нет данных.” Never trigger on merely old/stale logs without active consent.

Before sending, reserve a private idempotency key `(owner, message-kind, local-date, exact-route)` under an exclusive lock. On success, read back the exact destination/message and mark delivered; on ambiguous transport failure, check destination before retrying. Cap at one reminder and one morning idea per local day; no replay/catch-up for missed days or DST transitions. Re-check cancellation and the journal state just before send. Do not publish the ledger, profile or message contents in the public repository. Test with a synthetic profile and a local-only route before enabling a real destination; stop if the route cannot be verified.

**Current implementation boundary:** the repo provides filtering and local candidates, not subscription storage, delivery-ledger code, live recipe ingredient guarantees, or a configured cron job. Those pieces are required before claiming active automated reminders. Each agent/runtime must implement and test them for its own delivery tool. Do not silently configure one during installation.
