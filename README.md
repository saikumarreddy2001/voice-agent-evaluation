# AI Voice Agent Evaluation

Python-based outbound AI patient built with LiveKit Agents to evaluate an AI medical receptionist through recorded, repeatable test scenarios.

## Technologies

- Python 3.12 and LiveKit Agents
- Deepgram — speech-to-text (STT)
- OpenAI GPT-4o-mini — language model (LLM)
- Cartesia — text-to-speech (TTS)
- Silero VAD — speech activity detection
- LiveKit SIP and Twilio — outbound telephone connectivity

## Project Overview

The agent plays the role of a patient and interacts with a medical receptionist at the authorized assessment destination. Ten scenarios cover common front-desk tasks as well as interruptions, corrections, ambiguity, and multiple requests. The repository includes call recordings, speaker-labeled transcripts, audio reports, and a documented bug report.

## Architecture and Design Decisions

The application uses a modular LiveKit Agents pipeline: Deepgram transcribes incoming speech, OpenAI GPT-4o-mini generates the AI patient's response, and Cartesia synthesizes spoken output. Silero VAD detects speech activity, while LiveKit `AgentSession` coordinates turns with `allow_interruptions=True`. Keeping STT, LLM, and TTS separate makes individual components easier to inspect, replace, and debug rather than relying on an end-to-end real-time speech-to-speech model. The tradeoff is additional network and processing latency between stages, which can affect turn-taking and interruption behavior.

Outbound calling is implemented through LiveKit SIP with Twilio telephony. Before a call, the application validates the outbound SIP trunk and approved caller ID, and dialing is restricted to the authorized destination. A separate receive-only LiveKit recorder joins the room before the call and captures both the AI patient and the receptionist without participating in the conversation. The workflow exports an MP3 recording and audio report, then attempts to generate a speaker-labeled transcript; if transcription fails, it can be retried from the saved stereo WAV file. This separation of telephony, conversation, recording, and transcription supports repeatable evidence-based analysis.

## Test Scenarios

1. Appointment booking (`appointment`)
2. Appointment rescheduling (`reschedule`)
3. Appointment cancellation (`cancellation`)
4. Prescription refill (`refill`)
5. Insurance inquiry (`insurance`)
6. Office hours (`office_hours`)
7. Interruption handling (`interruption`)
8. Ambiguous requests (`ambiguity`)
9. Corrections (`correction`)
10. Multiple requests (`multiple_requests`)

## Setup (Windows PowerShell)

1. Install Python 3.12 and FFmpeg, and ensure FFmpeg is available on `PATH`.
2. Clone this private repository and open its folder in PowerShell.
3. Create the virtual environment and install dependencies:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and fill in the credentials and settings for your own authorized environment:

   ```powershell
   Copy-Item .env.example .env
   ```

   The template lists the LiveKit, OpenAI, Deepgram, Cartesia, SIP trunk, caller ID, and telephony configuration variables. Never commit `.env` or publish real credentials.

## Running the Agent and Tests

Start the LiveKit worker in one terminal:

```powershell
.\.venv\Scripts\python.exe agent.py dev
```

In a second terminal, inspect a scenario without dialing:

```powershell
.\.venv\Scripts\python.exe make_call.py --scenario appointment
```

Verify the configured SIP trunk without dialing:

```powershell
.\.venv\Scripts\python.exe make_call.py --scenario appointment --verify-trunk
```

**Billable operation — only run with authorization and available provider credits:**

```powershell
.\.venv\Scripts\python.exe make_call.py --scenario appointment --call
```

The `--call` flag explicitly initiates the outbound telephone call. Do not run it for a dry run. The code restricts dialing to the authorized assessment number and checks the approved caller ID.

If automatic transcription fails and the stereo WAV recording is available, retry it with:

```powershell
.\.venv\Scripts\python.exe transcribe.py "recordings/<recording-name>.wav"
```

Replace `<recording-name>` with the actual recording filename. Transcription can incur API usage.

## Evidence

The `recordings/` directory contains ten MP3 call recordings, corresponding transcripts, and audio reports. The recorder captures both sides of the conversation. Review these files alongside the documented findings rather than relying on an isolated transcript excerpt.

## Bug Reports

See [`report/voice_bot_bug_report.md`](report/voice_bot_bug_report.md) for observed receptionist behavior, severity, reproduction details, and evidence references. The report distinguishes receptionist issues from AI-patient behavior.

## Security and Scope

- `.env` contains local credentials and is excluded from Git; `.env.example` contains placeholders only.
- Use only the authorized assessment destination and approved outbound caller ID.
- No real-time speech-to-speech model or hosted voice-agent platform is used.
- Calls and transcription may incur charges; dry-run commands do not dial.
