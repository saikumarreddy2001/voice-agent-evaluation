
"""
LOCAL MICROPHONE TEST - AI PATIENT

Pipeline:
    Microphone -> Deepgram STT -> OpenAI LLM
    -> Cartesia TTS -> Computer speakers

Run:
    .\\.venv\\Scripts\\python.exe test_local.py console

No telephone calls are placed.
API usage may incur charges.
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import (
    cartesia,
    deepgram,
    openai,
    silero,
)

from agent import PatientAgent
from scenarios import list_scenarios


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    BASE_DIR / ".env",
    override=True,
)

logger = logging.getLogger("local.patient.test")

DEFAULT_SCENARIO = "appointment"


def get_scenario_name():
    scenario = os.getenv(
        "LOCAL_TEST_SCENARIO",
        DEFAULT_SCENARIO,
    ).strip().lower()

    if scenario not in list_scenarios():
        raise ValueError(
            f"Unknown scenario: {scenario}. "
            f"Available: {list_scenarios()}"
        )

    return scenario


def register_diagnostics(session):

    @session.on("user_input_transcribed")
    def on_user_transcribed(event):
        transcript = getattr(
            event,
            "transcript",
            "",
        )

        is_final = getattr(
            event,
            "is_final",
            False,
        )

        if transcript:
            logger.info(
                "RECEPTIONIST HEARD (final=%s): %s",
                is_final,
                transcript,
            )

    @session.on("conversation_item_added")
    def on_conversation_item(event):
        item = getattr(event, "item", None)

        if item is None:
            return

        role = getattr(item, "role", "unknown")
        content = getattr(item, "content", "")

        logger.info(
            "CONVERSATION [%s]: %s",
            role,
            str(content)[:1500],
        )

    @session.on("user_state_changed")
    def on_user_state(event):
        logger.info(
            "RECEPTIONIST STATE: %s -> %s",
            getattr(event, "old_state", "?"),
            getattr(event, "new_state", "?"),
        )

    @session.on("agent_state_changed")
    def on_agent_state(event):
        logger.info(
            "AI PATIENT STATE: %s -> %s",
            getattr(event, "old_state", "?"),
            getattr(event, "new_state", "?"),
        )

    @session.on("error")
    def on_error(event):
        logger.error(
            "VOICE PIPELINE ERROR: %s",
            getattr(event, "error", event),
        )


async def entrypoint(ctx: JobContext):

    scenario_name = get_scenario_name()

    print("\n" + "=" * 55)
    print("LOCAL AI PATIENT MICROPHONE TEST")
    print("=" * 55)
    print(f"Scenario: {scenario_name}")
    print("You are the RECEPTIONIST.")
    print("The AI is the PATIENT: Alex Morgan.")
    print("No telephone call will be placed.")
    print("=" * 55 + "\n")

    required_keys = [
        "DEEPGRAM_API_KEY",
        "OPENAI_API_KEY",
        "CARTESIA_API_KEY",
        "CARTESIA_VOICE_ID",
    ]

    missing = [
        key
        for key in required_keys
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            "Missing environment variables: "
            + ", ".join(missing)
        )

    logger.info("Loading speech components...")

    session = AgentSession(
        stt=deepgram.STT(),
        llm=openai.LLM(
            model="gpt-4o-mini",
        ),
        tts=cartesia.TTS(
            voice=os.environ[
                "CARTESIA_VOICE_ID"
            ],
        ),
        vad=silero.VAD.load(),
        allow_interruptions=True,
    )

    register_diagnostics(session)

    patient = PatientAgent(
        scenario_name=scenario_name,
    )

    logger.info("Starting local patient session...")

    try:
        await session.start(
            agent=patient,
            room=ctx.room,
        )

        await ctx.connect()

        print("\n" + "=" * 55)
        print("LOCAL SESSION READY")
        print("=" * 55)
        print("Speak into your microphone.")
        print()
        print("Suggested first question:")
        print(
            "Thank you for calling Pivot Point "
            "Orthopedics. How may I help you?"
        )
        print()
        print("Wait for Alex Morgan to respond.")
        print("Then ask follow-up questions.")
        print()
        print("Press Ctrl+C to stop.")
        print("=" * 55 + "\n")

        # No forced opening message.
        # The patient should listen first.
        # AgentSession handles subsequent turns.

        await asyncio.Event().wait()

    except asyncio.CancelledError:
        logger.info("Local test stopped.")
        raise

    finally:
        logger.info("Closing local session...")
        await session.aclose()


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s"
        ),
    )

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
