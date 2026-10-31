# Evidence and safety boundaries

This package records observations and makes charts. It does not prescribe treatment or infer nutritional deficiencies. The references below inform the agent's *conversation*, not automatic targets in code.

- [WHO physical activity fact sheet](https://www.who.int/news-room/fact-sheets/detail/physical-activity): population-level activity guidance, including adult aerobic and muscle-strengthening activity. Adapt to the person's condition and ability; never use it to pressure someone through pain.
- [WHO healthy diet fact sheet](https://www.who.int/news-room/fact-sheets/detail/healthy-diet): population-level diet guidance, not an individual calorie budget or a basis for supplement dosing.
- [ACSM progression models in resistance training, PubMed](https://pubmed.ncbi.nlm.nih.gov/19204579/): progression depends on training status. The skill records sets/reps/load but does not autonomously increase them.
- [ISSN position stand on protein and exercise, PubMed](https://pubmed.ncbi.nlm.nih.gov/28642676/): a training-population context for protein discussions, not a universal prescription for every user.
- [NIH Office of Dietary Supplements nutrient recommendations](https://ods.od.nih.gov/HealthInformation/nutrientrecommendations.aspx): RDA, AI and UL differ, and intake reference values depend on age and other factors. Logged micronutrient amounts are **not** diagnoses or lab results; missing database fields are unknown, not zero.
- [USDA FoodData Central API guide](https://fdc.nal.usda.gov/api-guide): source and units for food composition. Food identification, cooking state and weighed portion must match before using the result. The API may list Energy in both kJ and kcal; code requires the kcal unit.
- [NIDDK Body Weight Planner](https://www.niddk.nih.gov/bwp): energy needs and weight trends are modeled estimates; this skill does not assert a predicted rate of weight change.
- [Study of image-based dietary estimation, PubMed](https://pubmed.ncbi.nlm.nih.gov/41138916/): food photographs can miss portions/hidden ingredients; treat a photo as an uncertain identification aid, not a laboratory measurement. Study accuracy is not a guarantee for this agent.

## Agent rules derived from these sources

1. Ask for the owner's consent before persistent logging, and confirm goals/limitations before giving training or calorie suggestions. Pain, pregnancy, eating-disorder concerns, significant medical issues or suspected deficiency call for a qualified professional.
2. Ask for food name, preparation, source and weighed serving when possible. For a photo, ask about oil, sauce and hidden ingredients; label remaining estimates explicitly.
3. Display recorded intake and its coverage, not a claim about the person's entire day. Missing days and missing nutrients are `null`/unknown rather than zero. Correct a record rather than appending a duplicate.
4. Discuss activity/protein population guidelines only with their context; no fixed caloric deficit, supplement dose, or training progression is automatically set.
5. Do not compare micronutrient bars to an RDA/UL without verified personal context and data coverage; even with a comparison, no diagnosis follows from a food log.
6. Send private charts only to the approved recipient. `trends` measures logged days, training minutes and weight changes from recorded entries; it does not grade adherence or health.

## Compared open agent skills

- [Hermes official fitness-nutrition](https://github.com/NousResearch/hermes-agent/tree/main/optional-skills/health/fitness-nutrition): useful exercise database and calculators; our lookup deliberately verifies `kcal` to avoid kJ confusion.
- [agent-fitness-coach food-log](https://github.com/kaustin923/agent-fitness-coach/tree/HEAD/.claude/skills/food-log): component-level portions/corrections are useful; automatic logging on any food mention is not adopted.
- [sparky-fitness](https://github.com/shovikghosh/shovik-skills/tree/HEAD/skills/sparky-fitness): source-first data entry and unknown ≠ zero; depends on external Sparky services, so not bundled.
- [fitness-coach-lite](https://github.com/youhan2021/fitness-coach-lite): low-friction chat logging; its training targets are not copied as medical standards.
- [evidence-based-fitness-coach](https://github.com/Lancetnik/evidence-based-fitness-coach): useful referral boundaries and uncertainty language; fixed deficits or timeline promises are not imported.

These are references, not runtime dependencies or endorsements. The upstream official Hermes skill is a separate optional install.
