# Visual report contract

A chart is a data artifact, not a diagnosis or a moral grade. The agent may use its image-generation tool for an editorial presentation of **synthetic** or owner-authorized private records, but must not trust generated numbers, labels, scales, or exercise claims without comparing every visible datum to `coach.py trends` and `report` output. Never upload a health record to an image provider without explicit informed consent for that external processing. If the user has consented only to local logs, use the verified local PNG renderer instead.

## Status and color semantics

- **Slate/gray — unknown:** missing meals, unconfirmed completeness, photo-estimated portions, unknown macros, no owner-approved goal, or incomplete nutrient coverage. Missing ≠ zero. Do not make the bar look like an explicit zero.
- **Teal — within an owner-approved range:** `weekly_range_status=within_user_range` only when all 7 food days were confirmed complete, an owner-approved weekly-average energy range was recorded, and no photo-estimated food was logged. This is agreement of **recorded energy** with a chosen plan, not proof of healthy eating. `food_complete` confirms the owner's report, not true completeness or nutrient accuracy.
- **Amber — review a difference from the owner's range:** `weekly_range_status=outside_user_range` under the same evidence gate. Never label it “bad,” “cheat,” “failed,” or “unhealthy.” A single day does not diagnose anything. When status is `null`, keep neutral, not red/amber.
- **Micronutrients:** display units, source and coverage only. No red/green deficiency grading from a food log, no fabricated DRI line. DRI/RDA/AI/UL differ and depend on the individual; even a complete log is not a lab test.
- **Activity:** distinguish “recorded workout” from “no record”; do not color a rest day negatively. Only compare completed vs planned activity when an owner-approved plan and complete workout log exist. Do not use calories burned as exact compensation for food.

## GPT Image workflow (optional)

1. Obtain explicit consent for sharing the selected **personal** report values with an external image provider; otherwise work entirely locally. Never send names, conditions, photos or exact medical details unless needed and explicitly authorized. Synthetic examples need no health-data consent.
2. Select the right packet: `coach.py snapshot --scope entry` just after a new entry, `--scope day` for an end-of-day view (includes Monday-to-today brief), `--scope week` for the ISO Monday–Sunday wrap-up. Run `report`/`trends` when needed for detailed verification. Freeze a short fact sheet of exact dates, units, numbers, missing entries, coverage and privacy-safe labels.
3. Provide the image model the fact sheet as hard constraints. Make an editorial mobile-first layout with restrained color, typography, information hierarchy and clear unknown states. Never ask it to estimate or invent missing values or personalized norms.
4. Inspect the returned image visually and compare **each** visible date, number, unit, mark and legend against the fact sheet. Reject pseudo-text, altered data, wrong day order, misleading bar lengths, clipping, or an unapproved traffic-light assessment. If any check fails, regenerate or fall back to the local verified PNG. Do not silently correct generated facts with code and call the result model-only.
5. Deliver as a native image to the explicitly specified chat only. A model-generated card is an *illustrated report* with a verification gate; it is not the canonical record. The local JSON journal and text report remain authoritative.

The model can make a more stylish single image, but it cannot guarantee exact charts. The CLI computes an optional **weekly recorded-energy range status** under strict coverage conditions; this is not a nutritional-quality score, a medical norm, or a safe clinical interpretation. Keep this limitation in the user-facing description.

## Three distinct jobs, not one repeated bar chart

- **On entry — compact receipt:** one confirmed meal/workout/weight and its source, today's recorded subtotal (if applicable), one short context line. Do not imply the day is complete or show a red goal shortfall while the day is ongoing. Deliver an image only if the person opted into image generation and private-data transfer; otherwise a compact text receipt is the safe default.
- **Day close — editorial day sheet:** logged food with measured-versus-estimated coverage, known macro and micronutrient amounts where available, activity recorded, then a small *week-to-date* strip labeled by logged days. Ask the user before `close-day --confirmed-by-user`; a later meal reopens that day.
- **Week close — distinct weekly spread:** ISO Monday–Sunday, recorded days/confirmed-complete days, average logged energy only **over those complete days**, activity minutes and training days as observations, and sparse weight points with dates. A blank day stays unknown. Do not compare generic workout minutes to WHO moderate/vigorous thresholds because the logger does not capture intensity; do not turn daily DRI values into a weekly allowance or infer deficiency from one week.

Avoid decorative gauges, continuous streaks, fake precision, and seven identical bars across every surface. Different layouts may share typography, materials, palette and accessibility contrast. Labels and numbers are facts; texture and composition are illustration. Read the report at Telegram thumbnail size before delivery.

## Art direction and prompt skeletons

Use a warm off-white canvas (`#F6F7F4`), deep ink type (`#14232B`), blue (`#135E7B`) for activity, muted teal (`#126B63`) for logged nutrition, violet (`#614B91`) for time-series context, and terracotta (`#9B3E35`) only as a restrained accent, **never a punishment**. Color always has a written status and a different mark/shape. Keep Russian labels short and the main fact visibly larger than decoration. These are design tokens, not computed health judgments. WCAG references and research links are in `EVIDENCE.md`.

For each scope, feed the **exact** current `snapshot` output through a minimal prompt. Replace brackets with verified values; never send a full raw journal to the image provider. If exact bar lengths matter, do not ask the model to draw them: send the canonical text/JSON or the local deterministic card instead.

- **Entry prompt:** “Square premium mobile receipt, editorial warm paper, one bold numeral. Copy exactly: [date], [logged item + measured portion or duration], [source / estimate label], [recorded day subtotal if applicable]. No goals, no progress ring, no other text. Simple abstract food/activity motif; no people. Neutral colors while day is open.”
- **Day prompt:** “Portrait day sheet for Telegram, single main recorded fact, below it clearly separated food coverage, known macros, activity and a quiet Monday-to-today line. Exact allowed text: [short immutable fact list]. Missing fields say ‘нет данных’; if day not owner-confirmed complete, do not show target percentage. Do not invent food groups, nutrients, calorie burn or medical conclusions.”
- **Week prompt:** “Square/portrait magazine spread, distinct nutrition and movement zones, one elegant sequence of date marks instead of seven identical bars. Exact allowed text: [ISO week start/end], [complete days / 7], [average recorded kcal on complete days or unknown], [observed activity minutes and days], [only actually recorded weight points]. No WHO completion badge without intensity and full activity history; no nutrient deficiency grading.”

Try one image-model draft, inspect every visible label/number/scale and contrast at phone size, then either one focused regeneration or send the exact local fallback. A beautiful wrong number is a failed report.
