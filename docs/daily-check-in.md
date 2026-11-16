# Daily psychological check-in

## 1. Test metadata

- **Name.** Daily sleep and perceived performance check-in.
- **Frequency.** The next form becomes available 24 hours after the account's last daily entry. Complete it at a comparable time relative to the start of the shift when possible.
- **Estimated time.** Less than 90 seconds for the five items. The supplemental measure is taken separately.
- **Variables.** Perceived sleep quality, energy, interference from stress, perceived clarity and attention, and effort required to maintain usual performance.

MediSpace uses its own wording. The domains draw on sleep and performance tracking in NASA Spaceflight Standard Measures. The scale and scoring require validation before use as an operational screening tool. [NASA Spaceflight Standard Measures](https://www.nasa.gov/humans-in-space/spaceflight-standard-measures-characterizing-how-humans-adapt-in-space/)

## 2. Items

Use a 1–5 agreement scale for all items. **1** strongly disagree, **2** disagree, **3** neither agree nor disagree, **4** agree, and **5** strongly agree.

| No. | Item | Variable |
| --- | --- | --- |
| 1 | My last sleep period allowed me to start the day well rested. | Restorative sleep |
| 2 | I have enough energy to maintain my usual work pace. | Perceived energy |
| 3 | My current stress makes it harder to do my tasks. | Interference from stress, reverse-scored |
| 4 | I can stay focused and follow the steps of my tasks clearly. | Perceived mental clarity and attention |
| 5 | Maintaining my usual pace takes more effort than normal. | Perceived effort, reverse-scored for comparison with item 2 |

The fifth item supports a descriptive comparison. A difference can reflect how the person interprets the question, changes at work, or other circumstances worth clarifying. The optional note captures this context.

## 3. Supplemental objective test

The 3-minute PVT-B presents visual stimuli at varying intervals and records the time to respond. To compare measurements, use the same protocol and device under comparable conditions. Record the current median and the individual's baseline median in milliseconds. The task takes place separately, and reporting the result in the daily check-in is optional. [PVT-B validation study](https://pubmed.ncbi.nlm.nih.gov/22025811/)

Both medians appear alongside the self-report for review. Add the time, shift, and testing conditions to the note when they provide context. The application keeps the objective measure and the subjective score separate.

## 4. Scoring and thresholds

| Measure | Calculation and display |
| --- | --- |
| Descriptive score | `100 × (R1 + R2 + (6 − R3) + R4 − 4) / 16`. The range is 0–100. A higher score represents more favorable responses on this form. |
| Consistency difference | `abs(R2 − (6 − R5))`. The range is 0–4 points, shown without classification. Item 5 is excluded from the score to avoid weighting energy twice. |
| Change in response time | `100 × (current median − baseline median) / baseline median`. A positive value indicates a slower response. The calculation requires two positive medians. |
| Missing data | All five items are required. The note and supplemental measure are optional. |
| Traffic-light categories | Pending validation. This form has no approved thresholds for green, yellow, or red. The application shows values and can request AI suggestions based on the entry for human review. |

**Save and generate AI follow-up** sends the completed items and the context provided. The original answers and the follow-up stay in the account holder's medical record. [WHO guidance on generative AI in health](https://www.who.int/publications/i/item/9789240084759)
