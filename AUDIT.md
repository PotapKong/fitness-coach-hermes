# Independent audit and improvement plan

Read-only review of public HEAD `edb7e844` on 2026-10-31: **6.5/10 for a local journal and reporting skill**, not a clinical tool or autonomous coach. The reviewer validated the Agent Skills structure and ran 11 unit tests; no live USDA, Telegram, scheduled delivery, recipe or clinical validation was performed. This is a scoped assessment, not a certification. Subsequent changes below are not part of that independent score.

## What was already strong

- `SKILL.md` separates a private, local-first journal from public code and requires consent for external image generation; `EVIDENCE.md` limits health claims and distinguishes weekly activity from daily dietary references.
- `coach.py` has a locked/atomic journal, numeric validation and event IDs; `food_lookup.py` distinguishes USDA kcal from kJ; `VISUAL.md` requires exact-fact checking rather than trusting generated text.
- The examples are synthetic. Unknown days are not called fasting; visual style is owner-selected rather than inferred from gender or body size.

## Findings and status

| Priority | Finding | Status / next action |
|---|---|---|
| P0 | No independently confirmed P0 in the audited scope. | Keep privacy and clinical boundaries in reviews. |
| P1 | A meal could carry `0` when calories were unknown; trends averaged open days. | Addressed after audit: optional `--kcal` becomes `null`, partial kcal coverage is explicit, averages use only owner-closed days whose every logged food has known kcal. Regression tests added. A verified literal zero remains distinct. |
| P1 | No reminders or daily morning recommendations existed. | `ideas.py` and a verified, extensible, short-link recipe catalog now produce **local candidate ideas**. Automatic delivery remains off until separate opt-ins, route, local schedule, quiet hours and safety preferences. See `AUTOMATION.md`; do not call this an active bot. |
| P1 | Allergies, restrictions and exercise limitations had no safe profile structure. | Candidate input accepts a private profile, fails closed for allergies/dietary exclusions and requires explicit preferences before suggesting activities. This is not full ingredient/allergen verification, medical clearance or a workout planner. |
| P2 | Entry receipt could accidentally describe the last event rather than the just-logged event. | Addressed by `snapshot --scope entry --event-id ...` with a regression for late/parallel entries. Callers must pass the stable event ID. |
| P2 | PNG directory privacy unchecked; tests did not OCR-check visual facts. | Private output directory is now validated; generated card factual QA and accessibility/mobile-scale checks remain manual. Add robust text/chart assertions and a second review pass before relying on external rendering. |
| P2 | Archived weekly example has a rejected empty-plate motif. | Remove or replace that archived asset in a future visual release; `README.md` marks it as a non-example in the meantime. |

## Follow-up review of the 0.6 candidate

A second read-only reviewer inspected the in-progress update mechanism, recipe picker and catalog. The review found an interruption window in the first updater design, several false ingredient hints caused by substring matches (`pea` in `peanut`/`chickpea`, avocado oil labelled as avocado), morning passive wait not counted against available time, and `allergies: null` treated like an explicit empty list. The release candidate now uses an atomic managed symlink pointer (previous release remains active until replacement), removes identified false hints, includes passive wait in morning ready-to-eat time, and withholds suggestions unless allergy/exclusion lists are explicitly confirmed. Regression tests were added. The reviewer did not re-score these later fixes: the **6.5/10 remains the old local-journal score**, not a claim about the whole newer coach. Auto-updating code from public `main` still trusts that repository's maintainer account and is opt-in; `UPDATES.md` offers check-only mode.

The 88 linked recipe pages were fetched with HTTP 200 and no canonical-link mismatches during this release check. This verifies availability at the check time, **not** ongoing accessibility, complete ingredient accuracy, nutritional values, allergy safety, licensing of full recipes, or fitness outcomes. No full recipe methods or source photos are included.

## Recommended next milestones

1. **Delivery gate.** Collect *separate* opt-ins for morning brief and missing-log reminder: IANA time zone, each local time, route including topic, quiet hours, rate cap and an easy pause/stop. Only then configure Hermes cron with a private `(owner, kind, local date, route)` delivery ledger. Confirm no-log is unknown, not evidence of not eating. Test DST, restart/retry, pause and send readback. No scheduled job has been created in this repo.
2. **Personalization.** Obtain explicitly chosen tastes, allergens/exclusions, kitchen equipment, time/budget and activity preferences/limitations. For allergies, withhold automated recipe selection until full source ingredient and packaging verification is implemented. Curate source-linked recipes with provenance and review dates; avoid copying full methods or making “healthy”/“PP” guarantees.
3. **Accuracy and visual QA.** Review computed nutrition and activity claims; test unknown vs literal zero, incomplete kcal coverage, delayed event receipts and permission failures. Add machine-checked card text/chart fixtures and smartphone-size legibility checks; use AI art only as presentation with exact local fact overlays.
4. **Independent re-audit.** Repeat read-only security, science, accessibility and real delivery tests after the delivery layer exists. Re-score the whole *coach* only then; the original 6.5/10 does not automatically rise when code changes.
