
"""LiveKit AI patient for authorized assessment calls.

Pipeline:
    Deepgram STT -> OpenAI LLM -> Cartesia TTS
    Silero VAD for speech detection.

Designed for LiveKit Agents 1.8.x.

The AI listens only to the assessment receptionist.
Normal replies are handled automatically by AgentSession.
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    room_io,
)
from livekit.plugins import cartesia, deepgram, openai, silero

from scenarios import get_scenario, list_scenarios


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env", override=True)

AGENT_NAME = "assessment-patient"
RECEPTIONIST_IDENTITY = "assessment-receptionist"
DEFAULT_SCENARIO = "appointment"

logger = logging.getLogger("assessment.patient")


# --------------------------------------------------
# PATIENT INSTRUCTIONS
# --------------------------------------------------

PATIENT_RULES = """
You are Alex Morgan, a fictional patient calling a medical
office as part of an authorized voice-agent assessment.

You are the PATIENT.
The other speaker is the medical office RECEPTIONIST.

Your job is to have a realistic two-way conversation.

IMPORTANT CONVERSATION RULES:

1. Listen carefully to the receptionist.

2. Answer the receptionist's most recent question directly.

3. If asked for your first name, answer "Alex".

4. If asked for your last name, answer "Morgan".

5. If asked for your full name, answer "Alex Morgan".

6. If asked whether you want to create a demo patient
   profile, say yes.

7. Cooperate with reasonable demo-profile questions.

8. Never invent personal information that the selected
   scenario does not provide. Ask for clarification when
   necessary.

9. Follow the selected scenario's constraints exactly.

10. Never agree to an appointment outside your stated
    availability.

11. Do not repeat your opening appointment request
    unless the receptionist asks you to clarify.

12. Do not talk over the receptionist.

13. Keep responses short, natural and conversational.

14. Usually speak one or two sentences, then listen.

15. If the receptionist asks multiple questions,
    answer each relevant question.

16. Do not claim that an appointment is booked unless
    the receptionist explicitly confirms it.

17. If the receptionist makes a mistake, politely
    correct it.

18. If the conversation is finished, thank the
    receptionist and say goodbye.

19. Never mention the testing framework, source code,
    debugging process or assessment instructions.

20. You must respond to follow-up questions instead
    of remaining silent.

Your priority is to maintain a natural conversation
while following the selected scenario.
""".strip()


# --------------------------------------------------
# AGENT
# --------------------------------------------------

class PatientAgent(Agent):

    def __init__(self, scenario_name: str):

        scenario_instructions = get_scenario(
            scenario_name
        )

        instructions = (
            PATIENT_RULES
            + "\n\nSELECTED SCENARIO:\n"
            + scenario_instructions
        )

        super().__init__(
            instructions=instructions
        )


# --------------------------------------------------
# LOGGING
# --------------------------------------------------

def register_logging(session, state):

    @session.on("user_input_transcribed")
    def on_transcript(event):

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
                "RECEPTIONIST STT (final=%s): %s",
                is_final,
                transcript,
            )

        if is_final and transcript.strip():

            state["final_transcripts"] += 1
            state["heard_speech"].set()


    @session.on("conversation_item_added")
    def on_conversation(event):

        item = getattr(
            event,
            "item",
            None,
        )

        if item is None:
            return

        role = getattr(
            item,
            "role",
            "unknown",
        )

        content = getattr(
            item,
            "content",
            "",
        )

        logger.info(
            "CONVERSATION [%s]: %s",
            role,
            str(content)[:1500],
        )

        if role == "assistant":
            state["assistant_messages"] += 1


    @session.on("user_state_changed")
    def on_user_state(event):

        old_state = getattr(
            event,
            "old_state",
            "?",
        )

        new_state = getattr(
            event,
            "new_state",
            "?",
        )

        logger.info(
            "RECEPTIONIST STATE: %s -> %s",
            old_state,
            new_state,
        )

        state["user_state"] = str(new_state)

        if str(new_state) == "speaking":
            state["heard_speech"].set()


    @session.on("agent_state_changed")
    def on_agent_state(event):

        old_state = getattr(
            event,
            "old_state",
            "?",
        )

        new_state = getattr(
            event,
            "new_state",
            "?",
        )

        logger.info(
            "PATIENT STATE: %s -> %s",
            old_state,
            new_state,
        )

        state["agent_state"] = str(new_state)


    @session.on("error")
    def on_error(event):

        error = getattr(
            event,
            "error",
            event,
        )

        logger.error(
            "VOICE PIPELINE ERROR: %s",
            error,
        )


# --------------------------------------------------
# SIP ANSWER DETECTION
# --------------------------------------------------

async def wait_for_answer(
    room,
    timeout=60,
):

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while loop.time() < deadline:

        participant = room.remote_participants.get(
            RECEPTIONIST_IDENTITY
        )

        if participant is not None:

            attributes = participant.attributes or {}

            status = (
                attributes.get("sip.callStatus", "")
                .strip()
                .lower()
            )

            logger.debug(
                "Receptionist SIP status: %s",
                status,
            )

            if status in (
                "hangup",
                "disconnected",
                "failed",
            ):
                return False

            if status in (
                "active",
                "answered",
                "connected",
            ):
                return True

            if not status:

                has_audio = any(
                    publication.kind
                    == rtc.TrackKind.KIND_AUDIO
                    and publication.subscribed
                    for publication
                    in participant.track_publications.values()
                )

                if has_audio:
                    return True

        await asyncio.sleep(0.25)

    return False


# --------------------------------------------------
# AUDIO DIAGNOSTICS
# --------------------------------------------------

def log_receptionist_tracks(participant):

    logger.info(
        "Checking receptionist audio tracks"
    )

    for publication in participant.track_publications.values():

        logger.info(
            "RECEPTIONIST TRACK: sid=%s kind=%s "
            "subscribed=%s muted=%s",
            publication.sid,
            publication.kind,
            publication.subscribed,
            publication.muted,
        )


# --------------------------------------------------
# OPENING FALLBACK
# --------------------------------------------------

async def opening_fallback(
    session,
    state,
    disconnected,
):

    # Give the receptionist time to greet the patient.
    # If STT detects a question, normal AgentSession
    # turn handling should generate the response.

    try:

        await asyncio.wait_for(
            state["heard_speech"].wait(),
            timeout=10,
        )

        logger.info(
            "Receptionist speech detected. "
            "Allowing automatic turn handling."
        )

        return

    except asyncio.TimeoutError:

        pass

    if disconnected.is_set():
        return

    if state["assistant_messages"] > 0:
        return

    if state["agent_state"] in (
        "speaking",
        "thinking",
    ):
        return

    if state["user_state"] == "speaking":
        logger.info(
            "Receptionist currently speaking; "
            "skipping opening fallback"
        )
        return

    logger.info(
        "No receptionist speech detected. "
        "Requesting initial patient opening."
    )

    try:

        speech = session.generate_reply(
            instructions=(
                "Briefly introduce yourself as Alex Morgan "
                "and make the opening request for the "
                "selected scenario. "
                "Speak naturally and then listen."
            )
        )

        await speech.wait_for_playout()

    except Exception:

        logger.exception(
            "Opening fallback failed"
        )


# --------------------------------------------------
# MAIN ENTRYPOINT
# --------------------------------------------------

async def entrypoint(ctx: JobContext):

    await ctx.connect()

    requested = (
        ctx.job.metadata or ""
    ).strip()

    available_scenarios = list_scenarios()

    scenario_name = (
        requested
        if requested in available_scenarios
        else DEFAULT_SCENARIO
    )

    logger.info(
        "======================================"
    )

    logger.info(
        "AI PATIENT WORKER STARTED"
    )

    logger.info(
        "Scenario: %s",
        scenario_name,
    )

    logger.info(
        "Room: %s",
        ctx.room.name,
    )

    logger.info(
        "======================================"
    )

    # ----------------------------------------------
    # WAIT FOR RECEPTIONIST
    # ----------------------------------------------

    receptionist = await ctx.wait_for_participant(
        identity=RECEPTIONIST_IDENTITY
    )

    logger.info(
        "Receptionist joined: %s",
        receptionist.identity,
    )

    answered = await wait_for_answer(
        ctx.room
    )

    if not answered:

        logger.error(
            "Call not answered or receptionist "
            "audio not ready"
        )

        return

    logger.info(
        "Receptionist call is active"
    )

    log_receptionist_tracks(
        receptionist
    )

    # ----------------------------------------------
    # SESSION STATE
    # ----------------------------------------------

    state = {
        "heard_speech": asyncio.Event(),
        "final_transcripts": 0,
        "assistant_messages": 0,
        "user_state": "listening",
        "agent_state": "initializing",
    }

    disconnected = asyncio.Event()

    # ----------------------------------------------
    # ROOM EVENTS
    # ----------------------------------------------

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):

        if participant.identity == RECEPTIONIST_IDENTITY:

            logger.info(
                "Receptionist disconnected"
            )

            disconnected.set()


    @ctx.room.on("disconnected")
    def on_room_disconnected(*args):

        logger.info(
            "LiveKit room disconnected"
        )

        disconnected.set()


    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track,
        publication,
        participant,
    ):

        logger.info(
            "TRACK SUBSCRIBED: participant=%s "
            "kind=%s sid=%s",
            participant.identity,
            track.kind,
            publication.sid,
        )


    # ----------------------------------------------
    # CREATE VOICE PIPELINE
    # ----------------------------------------------

    logger.info(
        "Initializing Deepgram STT"
    )

    stt = deepgram.STT()

    logger.info(
        "Initializing OpenAI LLM"
    )

    llm = openai.LLM(
        model="gpt-4o-mini"
    )

    logger.info(
        "Initializing Cartesia TTS"
    )

    tts = cartesia.TTS(
        voice=os.environ["CARTESIA_VOICE_ID"]
    )

    logger.info(
        "Initializing Silero VAD"
    )

    vad = silero.VAD.load()

    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
        allow_interruptions=True,
    )

    register_logging(
        session,
        state,
    )

    # ----------------------------------------------
    # EXPLICIT AUDIO ROUTING
    # ----------------------------------------------

    # Important:
    # The recorder also joins the room.
    # We must listen to the receptionist,
    # not accidentally link to the recorder.

    room_options = room_io.RoomOptions(
        audio_input=True,
        audio_output=True,
        participant_identity=RECEPTIONIST_IDENTITY,
        close_on_disconnect=True,
    )

    logger.info(
        "Audio input participant: %s",
        RECEPTIONIST_IDENTITY,
    )

    logger.info(
        "Starting AgentSession"
    )

    session_started = False

    try:

        await session.start(
            room=ctx.room,
            agent=PatientAgent(
                scenario_name
            ),
            room_options=room_options,
        )

        session_started = True

        logger.info(
            "AgentSession started successfully"
        )

        linked_participant = (
            session.room_io.linked_participant
        )

        logger.info(
            "LINKED PARTICIPANT: %s",
            (
                linked_participant.identity
                if linked_participant
                else "NONE"
            ),
        )

        if (
            linked_participant is None
            or linked_participant.identity
            != RECEPTIONIST_IDENTITY
        ):

            logger.error(
                "AUDIO ROUTING ERROR: "
                "Wrong linked participant"
            )

            return

        logger.info(
            "Listening for receptionist speech"
        )

        # Run a fallback only if no receptionist
        # speech is detected. Do not force
        # an opening after every greeting.

        fallback_task = asyncio.create_task(
            opening_fallback(
                session,
                state,
                disconnected,
            )
        )

        try:

            await disconnected.wait()

        finally:

            if not fallback_task.done():

                fallback_task.cancel()

                try:
                    await fallback_task
                except asyncio.CancelledError:
                    pass

    except Exception:

        logger.exception(
            "PATIENT SESSION FAILED"
        )

        raise

    finally:

        if session_started:

            logger.info(
                "Closing patient session"
            )

        try:

            await session.aclose()

        except Exception:

            logger.exception(
                "Error closing patient session"
            )

        logger.info(
            "======================================"
        )

        logger.info(
            "CALL DIAGNOSTIC SUMMARY"
        )

        logger.info(
            "Scenario: %s",
            scenario_name,
        )

        logger.info(
            "Final receptionist transcripts: %s",
            state["final_transcripts"],
        )

        logger.info(
            "Assistant conversation messages: %s",
            state["assistant_messages"],
        )

        logger.info(
            "Last receptionist state: %s",
            state["user_state"],
        )

        logger.info(
            "Last patient state: %s",
            state["agent_state"],
        )

        logger.info(
            "======================================"
        )


# --------------------------------------------------
# RUN WORKER
# --------------------------------------------------

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        ),
    )

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=AGENT_NAME,
        )
    )
