# Design framework for psychological support

AI helps design and structure preventive screening tools, operational monitoring surveys, and cognitive performance tests for isolated, confined, and extreme (ICE) environments. The responsible team reviews its proposals. Its role is limited to design and follow-up. Professionals are responsible for diagnosis, clinical care, and fitness-for-duty decisions.

## Reference frameworks

- **NASA Behavioral Health and Performance (BHP).** Use publicly available Johnson Space Center materials on behavioral health and individual and team performance. Apply the context of the ISS, Artemis, or proposed Mars missions based on the evidence available for each setting. [NASA BHP](https://www.nasa.gov/reference/jsc-behavioral-health/)
- **NASA Spaceflight Standard Measures.** Consider comparable measures of sleep, mood, cognitive performance, and cohesion, including comparisons between subjective and objective measures. [NASA Spaceflight Standard Measures](https://www.nasa.gov/humans-in-space/spaceflight-standard-measures-characterizing-how-humans-adapt-in-space/)
- **Analog missions.** Consider Mars500 (IBMP/ESA, 520 days), HI-SEAS, HERA, and Antarctic stations such as Concordia and McMurdo. Identify the original setting and the limits of transferring findings from an analog to another mission. [NASA Human Factors and Behavioral Performance](https://www.nasa.gov/hrp/human-factors-and-behavioral-performance/)

| Instrument | Variables that inform the design |
| --- | --- |
| PHQ-9 | Interest, mood, fatigue, appetite, self-appraisal, and psychomotor changes. [Original study](https://pmc.ncbi.nlm.nih.gov/articles/PMC1495268/) |
| GAD-7 | Nervousness, hard-to-control worry, restlessness, and irritability. [Original study](https://pubmed.ncbi.nlm.nih.gov/16717171/) |
| STAI | Distinguishes trait anxiety from state anxiety after a technical failure, EVA, or emergency. |
| POMS | Tension, depression, hostility, vigor, fatigue, and confusion. |
| PSQI and KSS | Sleep latency, awakenings, sleep efficiency, perceived rest, and subjective sleepiness. |
| PVT | Reaction time and attention lapses. Record the version, duration, device, and definition of a lapse. The original request proposes lapses over 500 ms and a brief 60-second test. Verify that this combination applies to the selected version before use. |

Each item, scale, metric, and threshold must be traceable to a source in these frameworks. Identify the source and validation status of each adaptation. Verify permissions before reproducing items from standardized instruments.

## Phenomena and indicators to consider

| Proposed phenomenon | Indicators proposed for monitoring |
| --- | --- |
| Depressive symptoms and the third-quarter phenomenon (Bechtel and Berning) | Loss of interest in tasks or recreation, feeling stuck, low motivation, and low energy. Compare shifts in morale or interpersonal tension with the mission phase. Treat the third-quarter phenomenon as a hypothesis to observe. |
| Operational anxiety, hypervigilance, and situational panic | Difficulty relaxing off duty, recurring concerns about technical failures, self-reported physical tension, and a feeling of losing control. Record timing relative to events such as depressurization, fires, or communications outages. |
| Space asthenization (Roscosmos and IBMP literature) | Mental fatigue during simple tasks, sensitivity to noise or light, irritability, emotional changes, and frustration tolerance. Record working conditions, noise, workload, and confinement for context. |
| Circadian disruption and sleep disturbances | Difficulty falling asleep, awakenings, unrefreshing sleep, reported use of sleep aids or stimulants, and on-duty sleepiness. Consider schedules and lighting conditions. |
| Space fog and cognitive changes | Perceived slowing, working memory lapses, difficulty paying attention, and operational errors. Record fatigue and environmental conditions, such as CO₂ if measurements are available, to review possible associations. |
| Isolation, withdrawal, and interpersonal conflict | Avoidance of group activities, communication difficulties, perceived unfair task allocation, irritation, and loneliness. Consider privacy and contact with family and mission control. |
| Break-off phenomenon (Clark and Graybiel) | Feelings of unreality, estrangement, emptiness, or emotional disconnection, including while looking at Earth or communicating with home. Record the context of the self-report. |

## Design and scoring

1. **Reduce underreporting.** Ask about effort, energy, and performance without clinical labels. Propose reverse-scored items to assess consistency when they can be worded clearly. Compare self-reports with comparable objective measures, such as reaction times or working memory accuracy, when available.
2. **Organize modules by frequency.** The daily module is designed for under 90 seconds using a 0–100 visual analog scale or a 1–5 Likert scale for sleep, energy, stress, and mental clarity. The weekly module is designed for 5–7 minutes. It draws on PHQ-9, GAD-7, POMS, and team cohesion and considers mission phase. The proposed post-critical-event module considers state anxiety using STAI and records the circumstances of the emergency or EVA.
3. **Document the scoring logic.** Specify the direction of each scale, how the baseline is established, the deviation formula, uncertainty, how missing data are handled, and the criteria for identifying discrepancies. The thresholds below are proposals for review and require evidence before operational use.

| Parameter in the original proposal | Threshold and action to review |
| --- | --- |
| Fatigue discrepancy | If a person reports no fatigue and performance drops by 20% from baseline, flag the discrepancy for review. Specify exactly how the drop is calculated, including the direction of the measure. |
| Green | 0–30% deviation. Follow the usual schedule if the responsible team confirms it is appropriate. |
| Yellow | 31–60% deviation or a discrepancy between self-report and test results. Review workload, rest, sleep hygiene, and self-regulation measures with the team. |
| Red | Over 60% deviation, a severe drop in performance, or critical signs of isolation or panic. Refer the situation to the team for confidential review. The responsible team decides whether to reassign duties. |

Before implementing traffic-light categories, check the boundaries, rounding between intervals, each instrument version, and the rule for combining scores. If evidence does not support a threshold, identify what still needs validation.

## Format for each proposal

1. **Test metadata.** Name, frequency, estimated time, and phenomena assessed.
2. **Items.** Numbered questions with their wording, response scale, measured variable, and source.
3. **Supplemental objective test.** A brief attention or memory exercise with test conditions and a metric for comparison with the self-report.
4. **Scoring and thresholds.** Formula and interpretation table with the sources and validation status of each threshold.

MediSpace includes the [daily check-in](daily-check-in.md) and the [weekly check-in](weekly-check-in.md). The post-emergency module is planned.

The profile's **Cognitive tests** section includes Motor Praxis. The browser measures the response time for each of the 20 consecutive targets. Completed rounds are saved in the account history and in `praxis_motora` in the JSON record.

The Visual Object Learning Test (VOLT) presents ten three-dimensional shapes for five seconds each. The immediate and delayed recognition rounds contain twenty shapes each. After immediate recognition, the server retains the session and makes delayed recognition available after fifteen minutes. The record stores both scores, the response times, and the actual interval in `memoria_visual`. The shapes are specific to MediSpace. [Delayed recognition description in Cognitive Atlas](https://cognitiveatlas.org/task/id/trm_56a2a98785453/)

The Line Orientation Test (LOT) presents twelve pairs of segments to match against a fan of eleven numbered lines. MediSpace uses angles from 15° to 165° and generates its own pairs. The record stores correct matches by pair and by line, response times, and answers in `orientacion_linea`. [Benton line orientation judgment reference](https://pmc.ncbi.nlm.nih.gov/articles/PMC3094715/)

## Support chat

The text chat offers emotional support and directs users to the health team when appropriate. The AI provider receives the message and recent turns to generate a reply. MediSpace stores the conversation in the account database separately from the downloadable JSON record.
