# Weekly psychological check-in

## 1. Test metadata

- **Name.** Weekly mood, performance, and team cohesion check-in.
- **Frequency.** The next form becomes available seven days after the account's last weekly entry. Each entry covers the preceding seven days.
- **Estimated time.** Between 5 and 7 minutes with the context note. The supplemental test is taken separately.
- **Domains.** Mood and interest, operational stress, sleep and performance, and team cohesion.

The form uses original MediSpace items. Its domains draw on aerospace monitoring of mood, sleep, and teams and the constructs of PHQ-9, GAD-7, and POMS. The wording, seven-day window, and scoring are specific to this form and require their own validation. [NASA Spaceflight Standard Measures](https://www.nasa.gov/reference/standard-measures/), [NASA evidence report on teams](https://ntrs.nasa.gov/citations/20220007465), [PHQ-9](https://pmc.ncbi.nlm.nih.gov/articles/PMC1495268/), [GAD-7](https://pubmed.ncbi.nlm.nih.gov/16717171/)

## 2. Items

Report how many of the past seven days each situation occurred. **1** no days, **2** 1–2 days, **3** 3–4 days, **4** 5–6 days, and **5** all seven days.

| No. | Item | Variable |
| --- | --- | --- |
| 1 | I found my tasks or leisure activities interesting. | Interest |
| 2 | Feeling discouraged disrupted my routine. | Interference from discouragement, reverse-scored |
| 3 | I finished my shift feeling ready to return to my usual activities. | Mood at the end of the shift |
| 4 | I found it hard to stop thinking about possible failures after my shift. | Operational concern, reverse-scored |
| 5 | Tension made it hard to relax while off duty. | Off-duty tension, reverse-scored |
| 6 | I was able to maintain a work pace that felt manageable. | Perceived workload management |
| 7 | I had enough energy to maintain my usual pace. | Perceived energy |
| 8 | Sleep helped me recover between shifts. | Recovery through sleep |
| 9 | I found it easy to stay focused on my tasks. | Perceived attention |
| 10 | I felt I could count on the crew during tasks. | Perceived support |
| 11 | I found it easy to communicate about work with the team. | Communication |
| 12 | I avoided team activities even when I wanted to take part. | Withdrawal, reverse-scored |
| 13 | I found it hard to maintain my energy during usual tasks. | Perceived effort, reverse-scored to compare with item 7 |

If an item depends on a situation that did not occur, use the note to explain the context. Both the mission and the note are optional. If there is only one active mission with complete dates, MediSpace suggests it in the form.

## 3. Supplemental objective test

The form accepts current and individual baseline medians from a 3-minute PVT-B performed separately. Record both in milliseconds using the same protocol and device under comparable conditions. The measurement appears next to the self-report in its original unit. [PVT-B validation study](https://pubmed.ncbi.nlm.nih.gov/22025811/)

## 4. Scoring and thresholds

For each domain, apply `25 × (mean of the three adjusted items − 1)`. A higher value represents more favorable responses within the domain. Reverse-scored items are calculated as `6 − response`.

| Measure | Calculation |
| --- | --- |
| Mood and interest | Items 1, 2 (reverse-scored), and 3. |
| Operational stress | Items 4 and 5 (reverse-scored), and 6. |
| Sleep and performance | Items 7, 8, and 9. |
| Team cohesion | Items 10, 11, and 12 (reverse-scored). |
| Energy comparison | `abs(R7 − (6 − R13))`, from 0 to 4 points. Item 13 is excluded from the domain scores. |
| Change in response time | `100 × (current median − baseline median) / baseline median`. A positive percentage indicates a longer response time. |
| Mission quarter | With valid start and end dates, `progress = elapsed UTC days / duration in days`. The quarters are 0 to under 25%, 25 to under 50%, 50 to under 75%, and 75 to 100%. The quarter is omitted outside the mission dates or when the duration cannot be calculated. |
| Traffic-light categories | Pending validation. Domain scores, the mission quarter, and changes in response time are shown as follow-up data without risk categories. |

If a person requests AI follow-up, the model receives their answers, descriptive scores, note, supplemental measurement, and mission quarter when available. The entry and follow-up are stored in `semanal_psicologico` in the account holder's JSON record. The mission quarter provides time context, and the responsible team reviews the suggested actions.
