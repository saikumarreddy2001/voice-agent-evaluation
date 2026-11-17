
"""Authorized outbound AI-patient assessment calls via LiveKit SIP.

Safe commands (do not place calls):
    python make_call.py --scenario appointment
    python make_call.py --scenario appointment --verify-trunk

Explicit paid call:
    python make_call.py --scenario appointment --call
"""

import argparse
import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from livekit import api

from recorder import LocalCallRecorder
from scenarios import get_test_objective, list_scenarios
from transcribe import generate_transcript

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

ALLOWED_DESTINATION = "+18054398008"
EXPECTED_CALLER = "+14143608649"
AGENT_NAME = "assessment-patient"
RECEPTIONIST_IDENTITY = "assessment-receptionist"
MAX_CALL_SECONDS = 300
RINGING_TIMEOUT_SECONDS = 45
WORKER_READY_TIMEOUT_SECONDS = 45
POLL_INTERVAL_SECONDS = 1
STATUS_GRACE_SECONDS = 5
ENDED_SIP_STATUSES = frozenset({"hangup", "disconnected", "failed"})


def validate_destination():
    destination = os.environ.get("ASSESSMENT_DESTINATION", ALLOWED_DESTINATION).strip()
    caller = os.environ.get("OUTBOUND_CALLER_NUMBER", "").strip()
    if destination != ALLOWED_DESTINATION:
        raise ValueError("Only the approved assessment destination is allowed.")
    if caller != EXPECTED_CALLER:
        raise ValueError("Outbound caller number does not match the approved configuration.")
    return destination


def create_client():
    return api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )


_TRUNK_ID_RE = re.compile(r"^ST_[0-9A-Za-z]{12}$")


def get_trunk_id():
    trunk_id = os.environ.get("LIVEKIT_OUTBOUND_TRUNK_ID", "").strip()
    if _TRUNK_ID_RE.fullmatch(trunk_id) is None:
        raise ValueError(
            "LIVEKIT_OUTBOUND_TRUNK_ID must be a LiveKit outbound "
            "trunk ID: ST_ followed by 12 letters or digits."
        )
    return trunk_id


async def check_trunk(client):
    trunk_id = get_trunk_id()
    response = await client.sip.list_sip_outbound_trunk(
        api.ListSIPOutboundTrunkRequest()
    )
    matching = [t for t in response.items if t.sip_trunk_id == trunk_id]
    if not matching:
        raise RuntimeError("Configured outbound SIP trunk was not found.")
    if EXPECTED_CALLER not in matching[0].numbers:
        raise RuntimeError("Approved caller ID is missing from the outbound trunk.")
    print("SUCCESS: SIP trunk verified; approved caller ID is configured.")
    return trunk_id


async def verify_trunk():
    validate_destination()
    client = create_client()
    try:
        await check_trunk(client)
    finally:
        await client.aclose()


def dry_run(scenario_name):
    if scenario_name not in list_scenarios():
        raise ValueError(f"Unknown scenario: {scenario_name}")
    objective = get_test_objective(scenario_name)
    print("\n=== DRY RUN (NO CALL) ===")
    print(f"Scenario: {scenario_name}")
    print(f"Destination: {validate_destination()}")
    print(f"Caller ID: {EXPECTED_CALLER}")
    print(f"Focus: {objective['focus']}")
    print(f"Expected: {objective['expected']}")
    print(f"Potential bug: {objective['potential_bug']}")
    print(f"Maximum answered-call duration: {MAX_CALL_SECONDS}s")
    print("No phone call was placed.")


async def list_room_participants(client, room_name):
    response = await client.room.list_participants(
        api.ListParticipantsRequest(room=room_name)
    )
    return response.participants


async def wait_for_worker(client, room_name):
    """Wait until the dispatched agent actually joins the room before dialing."""
    deadline = asyncio.get_running_loop().time() + WORKER_READY_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        participants = await list_room_participants(client, room_name)
        agents = [
            p for p in participants
            if p.identity not in {RECEPTIONIST_IDENTITY, "assessment-recorder"}
        ]
        if agents:
            print("SUCCESS: AI worker joined LiveKit room:", agents[0].identity)
            print("NOTE: Joined does not guarantee the speech pipeline is healthy.")
            return agents[0].identity
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(
        "AI worker did not join within 45 seconds. No phone call was placed. "
        "Start 'python agent.py dev' in Terminal 1 and check its logs."
    )


async def wait_for_call_end(client, room_name, deadline):
    loop = asyncio.get_running_loop()
    missing_since = None
    last_status = None
    while True:
        now = loop.time()
        if now >= deadline:
            print("Maximum answered-call duration reached.")
            return "timeout"
        participants = await list_room_participants(client, room_name)
        participant = next(
            (p for p in participants if p.identity == RECEPTIONIST_IDENTITY), None
        )
        if participant is None:
            if missing_since is None:
                missing_since = now
            elif now - missing_since >= STATUS_GRACE_SECONDS:
                print("Receptionist disconnected.")
                return "disconnected"
        else:
            missing_since = None
            status = (participant.attributes or {}).get("sip.callStatus", "").lower()
            if status != last_status:
                print("SIP status:", status or "<not supplied>")
                last_status = status
            if status in ENDED_SIP_STATUSES:
                return status
            disconnected_state = getattr(api.ParticipantInfo.State, "DISCONNECTED", None)
            if disconnected_state is not None and participant.state == disconnected_state:
                return "disconnected"
        await asyncio.sleep(min(POLL_INTERVAL_SECONDS, max(0, deadline - loop.time())))


def report_audio_quality(mp3_path):
    path = Path(mp3_path).with_name(Path(mp3_path).stem + "_audio_report.json")
    if not path.exists():
        print("WARNING: No audio report found; two-sided speech not verified.")
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        patient = report.get("patient_audio", {})
        receptionist = report.get("receptionist_audio", {})
        print("\n=== AUDIO ACTIVITY CHECK ===")
        print("Patient active seconds:", patient.get("active_seconds", "unknown"))
        print("Receptionist active seconds:", receptionist.get("active_seconds", "unknown"))
        if not report.get("both_sides_have_audio_activity", False):
            print("WARNING: One or both channels appear silent.")
            print("DO NOT count this call toward the 10 successful recordings.")
            return False
        print("Both channels contain audio activity; listen to confirm actual dialogue.")
        return True
    except (OSError, ValueError, TypeError) as exc:
        print(f"WARNING: Could not read audio report: {exc}")
        return None


async def save_transcript(mp3_path):
    wav_path = Path(mp3_path).with_suffix(".wav")
    if not wav_path.is_file():
        print("WARNING: WAV missing; cannot generate transcript.")
        return None
    print("\nGenerating speaker-labeled transcript (may incur API usage)...")
    try:
        transcript_path = await generate_transcript(wav_path)
        print(f"Transcript saved: {transcript_path}")
        return transcript_path
    except Exception as exc:
        print(f"WARNING: Transcription failed: {exc}")
        print(f'Retry later: python transcribe.py "{wav_path}"')
        return None


async def place_call(scenario_name):
    """Only called after the user explicitly supplies --call."""
    destination = validate_destination()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    room_name = f"patient-test-{uuid.uuid4().hex[:12]}"
    output_name = f"{stamp}_{scenario_name}"
    client = create_client()
    recorder = LocalCallRecorder(room_name, output_name)
    room_created = False
    recording_started = False
    call_answered = False
    end_reason = "not_started"
    try:
        trunk_id = await check_trunk(client)
        await client.room.create_room(
            api.CreateRoomRequest(name=room_name, empty_timeout=300)
        )
        room_created = True
        print(f"Room created: {room_name}")

        await recorder.start()
        recording_started = True
        print("Recorder initialized.")

        await client.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                room=room_name, agent_name=AGENT_NAME, metadata=scenario_name
            )
        )
        print("Agent dispatched. Waiting for worker to join BEFORE dialing...")
        await wait_for_worker(client, room_name)

        print(f"Dialing approved destination: {destination}")
        # This is the ONLY operation that initiates a paid telephone call.
        result = await client.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=destination,
                sip_number=EXPECTED_CALLER,
                room_name=room_name,
                participant_identity=RECEPTIONIST_IDENTITY,
                participant_name="Assessment Receptionist",
                wait_until_answered=True,
                ringing_timeout=timedelta(seconds=RINGING_TIMEOUT_SECONDS),
                max_call_duration=timedelta(seconds=MAX_CALL_SECONDS),
            )
        )
        call_answered = True
        end_reason = "in_progress"
        print("SUCCESS: Telephone call answered.")
        print("Receptionist participant:", result.participant_identity)
        print("Waiting for hangup or 300-second limit...")
        deadline = asyncio.get_running_loop().time() + MAX_CALL_SECONDS
        end_reason = await wait_for_call_end(client, room_name, deadline)
        print("Call ended:", end_reason)
    except asyncio.CancelledError:
        print("Call cancelled; cleaning up.")
        raise
    except Exception as exc:
        print(f"CALL ERROR: {exc}")
        raise
    finally:
        # Do not leave an active phone call connected if any part fails.
        if room_created:
            try:
                await client.room.remove_participant(
                    api.RoomParticipantIdentity(
                        room=room_name, identity=RECEPTIONIST_IDENTITY
                    )
                )
            except Exception:
                pass  # May already have disconnected, or may never have joined.

        if recording_started:
            try:
                print("\nFinalizing recording...")
                path = await recorder.stop()
                if path:
                    print("Saved MP3:", path)
                    if not call_answered:
                        print("WARNING: Call was not confirmed answered.")
                    report_audio_quality(path)
                    await save_transcript(path)
                else:
                    print("WARNING: No recording available for transcription.")
            except Exception as exc:
                print(f"Recording/transcription error: {exc}")

        if room_created:
            try:
                await client.room.delete_room(api.DeleteRoomRequest(room=room_name))
                print("Temporary LiveKit room deleted.")
            except Exception as exc:
                print(f"Room cleanup warning: {exc}")
        await client.aclose()


async def main():
    parser = argparse.ArgumentParser(description="Authorized AI Patient Voice Assessment")
    parser.add_argument("--scenario", choices=list_scenarios(), default="appointment")
    parser.add_argument("--verify-trunk", action="store_true", help="Check SIP trunk without dialing")
    parser.add_argument("--call", action="store_true", help="EXPLICITLY place a billable phone call")
    args = parser.parse_args()
    dry_run(args.scenario)
    if args.verify_trunk:
        await verify_trunk()
    if args.call:
        await place_call(args.scenario)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
