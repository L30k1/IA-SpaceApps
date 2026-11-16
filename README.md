# MediSpace

**[Open MediSpace on Render](https://ia-spaceapps.onrender.com/index.html)**

MediSpace is a web app for recording and reviewing astronaut health. It brings together each account’s medical record, mission assessments, and results history.

## Features

- **Medical monitoring.** Records heart rate, oxygen saturation, and temperature. Gemini generates questions and follow-up recommendations based on the conversation, the readings, and the personal reference ranges in the medical record.
- **Psychological support.** Includes daily and weekly check-ins, a support chat, and an emergency voice chat. The emergency chat guides users to contact the team responsible for emergency response.
- **Cognitive tests.** Includes Motor Praxis (MP), Visual Object Learning Test (VOLT), Line Orientation Test (LOT), Fractal 2-Back (F2B), and Facial Emotion Recognition (ERT). Results are saved in the history.
- **Missions and exercise.** The profile shows the assessment schedule and the mission’s daily exercise minimum. Mission dates come from the medical record.

## Getting started on Render

1. Open the [online version](https://ia-spaceapps.onrender.com/index.html).
2. Under **Create account**, enter your name, astronaut ID, and a password between 8 and 128 characters. Attach a medical history JSON file with the same name and ID.
3. If you need to generate a medical record, select **Create a medical history JSON file** and complete the form. When you download it, MediSpace takes you back to **Create account**.
4. To sign in again, use the account name, astronaut ID, and password.

### Demo account

If you cannot create a new medical history JSON file, select **Sign in** and use the demo account below.

| Field | Value |
| --- | --- |
| Name | **Sally K. Ride** |
| Astronaut ID | `1234` |
| Password | `12345678` |
| Editing key | `12345678` |

Use the editing key when MediSpace prompts you to unlock changes to the medical record.

## Use of AI

The [AI use disclosure](docs/ai-use-disclosure.md) describes how AI was used for images, audio, code, and data. The [provenance inventory](docs/ai-provenance.json) contains the metadata. AI assisted in developing the cognitive tests, and the app scores them using predefined rules.
