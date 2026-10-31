# Optional morning ideas and missing-log reminders

Nothing in this skill sends messages or creates scheduled jobs by itself. `ideas.py` returns a **read-only local candidate** with a source URL; `automation_core.py` implements consent/time/dedupe/readback state, but **no transport adapter**. Hermes cron and the user's platform deliver only after separate, explicit opt-ins. The absence of a food/workout entry is unknown, not proof of missed eating, a skipped workout or a failed goal.

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

Use [Hermes cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) **only after** the user has approved the exact details; create distinct morning and reminder jobs. `automation_core.py` offers `configure`, `reserve`, `pre_send`, `acknowledge` and `revoke` for a private `0600` state outside the skill/repo. `configure` requires an explicit per-owner consent flag, kind, exact route (`local` for synthetic tests, or confirmed `telegram:CHAT_ID[:TOPIC_ID]` for a real adapter), IANA zone, local time, quiet hours and existing private `0600` journal/profile files in a private `0700` directory. No destination is derived from gateway metadata. A scheduled adapter calls `reserve` at most once near the approved time; it returns `None` when canceled, out of window, quiet, duplicate or lacking a candidate. The morning candidate is a source-linked idea and optional non-prescriptive activity. The reminder reads today's active food records; no record triggers a neutral question, never a claim about what was eaten. The adapter calls `pre_send` **once as an atomic send claim** immediately before sending; a second worker gets false. Then send through the native platform and verify the exact destination/message ID before `acknowledge`. Never emit a nutrition target or silently convert a candidate into an eaten meal.

`reserve` locks an at-most-once key `(owner, kind, local-date)` **across routes** and stores a reservation nonce bound to its consent generation. On successful delivery, read back the exact destination/message and `acknowledge` with the nonce, exact route and platform message ID. On ambiguous failure, **do not retry automatically**: the reservation remains reserved/claimed until a human verifies the destination; otherwise retry risks duplicate delivery. `pre_send` atomically claims once, re-checking cancellation, local time, quiet hours, today's journal (reminders) and an unchanged profile/catalog fingerprint (ideas). Profile changes or reconfiguration invalidate a pending old idea rather than risk mismatched advice; a changed route does not permit a second delivery on the same day. Cap at one reservation of each kind per local day; no replay/catch-up for missed days or DST transitions. `revoke` disables future sends and invalidates its consent generation, but the adapter must also disable the matching cron job. Do not publish the ledger, profile or message contents. Test with a synthetic profile and local-only route; stop if a real adapter cannot verify the exact destination.

**Current implementation boundary:** subscription and ledger primitives exist and are unit-tested; an actual Hermes/Telegram transport, successful remote readback, subscription-specific cron installation/cancellation, and live recipe ingredient guarantees remain **unimplemented/unverified**. `acknowledge` trusts a message ID supplied by the adapter; it cannot independently prove delivery. Do not silently configure notifications during installation or call this a working autonomous delivery system. The separate code-update cron does not imply consent to health messages.
