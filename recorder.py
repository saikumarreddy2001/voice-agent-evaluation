
"""
Local LiveKit Call Recorder

Records both sides of an authorized assessment call.

Outputs:
    recordings/<name>.wav
    recordings/<name>.mp3
    recordings/<name>_audio_report.json

Stereo channels:
    LEFT  = AI patient
    RIGHT = receptionist

Includes audio-level validation to detect silent calls.
"""

import asyncio
import json
import os
import subprocess
import time
import wave

from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from livekit import api, rtc


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

SAMPLE_RATE = 48000
CHANNELS = 2

RECEPTIONIST_IDENTITY = "assessment-receptionist"
RECORDER_IDENTITY = "assessment-recorder"

# Minimum audio activity for a usable recording.
# These are diagnostic thresholds, not proof of speech.
MIN_PEAK_DBFS = -45.0
MIN_ACTIVE_SECONDS = 0.5
ACTIVE_FRAME_DBFS = -45.0

ANALYSIS_FRAME_SECONDS = 0.02


# --------------------------------------------------
# AUDIO ANALYSIS
# --------------------------------------------------

def analyze_audio(audio):
    """
    Analyze signal levels.

    Detects meaningful audio activity but cannot distinguish
    speech from background noise or tones.
    """

    if audio.size == 0:
        return {
            "peak_dbfs": -120.0,
            "rms_dbfs": -120.0,
            "active_seconds": 0.0,
            "duration_seconds": 0.0,
            "has_audio_activity": False,
        }

    samples = audio.astype(np.float64)

    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples * samples)))

    def to_dbfs(value):
        if value <= 0:
            return -120.0

        return float(
            20.0 * np.log10(value / 32768.0)
        )

    peak_dbfs = to_dbfs(peak)
    rms_dbfs = to_dbfs(rms)

    frame_size = max(
        1,
        int(SAMPLE_RATE * ANALYSIS_FRAME_SECONDS),
    )

    active_samples = 0

    for start in range(0, len(samples), frame_size):
        frame = samples[start:start + frame_size]

        if frame.size == 0:
            continue

        frame_rms = float(
            np.sqrt(np.mean(frame * frame))
        )

        if to_dbfs(frame_rms) >= ACTIVE_FRAME_DBFS:
            active_samples += len(frame)

    active_seconds = active_samples / SAMPLE_RATE

    has_audio_activity = (
        peak_dbfs >= MIN_PEAK_DBFS
        and active_seconds >= MIN_ACTIVE_SECONDS
    )

    return {
        "peak_dbfs": round(peak_dbfs, 2),
        "rms_dbfs": round(rms_dbfs, 2),
        "active_seconds": round(active_seconds, 2),
        "duration_seconds": round(
            len(samples) / SAMPLE_RATE,
            2,
        ),
        "has_audio_activity": bool(has_audio_activity),
    }


# --------------------------------------------------
# RECORDER
# --------------------------------------------------

class LocalCallRecorder:
    """Record both sides of a LiveKit call."""

    def __init__(self, room_name: str, output_name: str):
        self.room_name = room_name
        self.output_name = output_name

        self.output_dir = BASE_DIR / "recordings"
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.room = rtc.Room()

        self.tasks = []
        self.participants = set()
        self.subscribed_tracks = set()

        self.started_at = None
        self.running = False

        self.audio_by_participant = {}
        self.track_start_times = {}

        self.recording_report = None

    # --------------------------------------------------
    # START RECORDING
    # --------------------------------------------------

    async def start(self):
        """Connect a receive-only recorder to LiveKit."""

        token = (
            api.AccessToken(
                os.environ["LIVEKIT_API_KEY"],
                os.environ["LIVEKIT_API_SECRET"],
            )
            .with_identity(RECORDER_IDENTITY)
            .with_name("Assessment Recorder")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=self.room_name,
                    can_subscribe=True,
                    can_publish=False,
                )
            )
            .to_jwt()
        )

        self.started_at = time.monotonic()
        self.running = True

        @self.room.on("track_subscribed")
        def on_track_subscribed(
            track,
            publication,
            participant,
        ):
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                self._subscribe(
                    track,
                    participant.identity,
                )

        await self.room.connect(
            os.environ["LIVEKIT_URL"],
            token,
        )

        # Capture tracks that existed before the
        # subscription event handler was triggered.
        for participant in self.room.remote_participants.values():
            for publication in participant.track_publications.values():
                track = publication.track

                if (
                    track
                    and track.kind == rtc.TrackKind.KIND_AUDIO
                ):
                    self._subscribe(
                        track,
                        participant.identity,
                    )

        print(f"Recorder connected: {self.room_name}")

    # --------------------------------------------------
    # SUBSCRIBE TO AUDIO
    # --------------------------------------------------

    def _subscribe(self, track, identity):
        """Subscribe to an audio track once."""

        track_id = (identity, track.sid)

        if track_id in self.subscribed_tracks:
            return

        self.subscribed_tracks.add(track_id)

        print(f"Audio track subscribed: {identity}")

        self.audio_by_participant.setdefault(
            identity,
            [],
        )

        task = asyncio.create_task(
            self._capture(track, identity)
        )

        self.tasks.append(task)

    # --------------------------------------------------
    # CAPTURE AUDIO
    # --------------------------------------------------

    async def _capture(self, track, identity):
        """Collect audio samples for one participant."""

        stream = rtc.AudioStream(
            track,
            sample_rate=SAMPLE_RATE,
            num_channels=1,
        )

        try:
            async for event in stream:
                if not self.running:
                    break

                samples = np.frombuffer(
                    event.frame.data,
                    dtype=np.int16,
                ).copy()

                if samples.size == 0:
                    continue

                if identity not in self.track_start_times:
                    elapsed = max(
                        0.0,
                        time.monotonic() - self.started_at,
                    )

                    self.track_start_times[identity] = max(
                        0,
                        int(elapsed * SAMPLE_RATE)
                        - len(samples),
                    )

                self.audio_by_participant[
                    identity
                ].append(samples)

                self.participants.add(identity)

        except asyncio.CancelledError:
            pass

        except Exception as exc:
            print(
                f"Audio capture error for {identity}: {exc}"
            )

        finally:
            await stream.aclose()

    # --------------------------------------------------
    # BUILD AUDIO
    # --------------------------------------------------

    def _build_participant_audio(
        self,
        identity,
        total_samples,
    ):
        """Build one aligned mono audio channel."""

        output = np.zeros(
            total_samples,
            dtype=np.float32,
        )

        if identity is None:
            return output

        chunks = self.audio_by_participant.get(
            identity,
            [],
        )

        if not chunks:
            return output

        start = self.track_start_times.get(
            identity,
            0,
        )

        samples = np.concatenate(
            chunks
        ).astype(np.float32)

        end = min(
            start + len(samples),
            total_samples,
        )

        if end > start:
            output[start:end] = samples[:end - start]

        return output

    # --------------------------------------------------
    # STOP RECORDING
    # --------------------------------------------------

    async def stop(self):
        """Finalize WAV, MP3, and audio validation report."""

        self.running = False

        for task in self.tasks:
            task.cancel()

        if self.tasks:
            await asyncio.gather(
                *self.tasks,
                return_exceptions=True,
            )

        await self.room.disconnect()

        valid_participants = [
            identity
            for identity, chunks
            in self.audio_by_participant.items()
            if chunks
        ]

        if not valid_participants:
            print("WARNING: No audio captured.")
            return None

        # Identify the AI patient and receptionist.
        # Exclude the recorder itself from consideration.
        patient_identities = [
            identity
            for identity in valid_participants
            if (
                identity != RECEPTIONIST_IDENTITY
                and identity != RECORDER_IDENTITY
            )
        ]

        patient_identity = (
            patient_identities[0]
            if patient_identities
            else None
        )

        def track_end(identity):
            if identity is None:
                return 0

            chunks = self.audio_by_participant.get(
                identity,
                [],
            )

            if not chunks:
                return 0

            return (
                self.track_start_times.get(
                    identity,
                    0,
                )
                + sum(
                    len(chunk)
                    for chunk in chunks
                )
            )

        total_samples = max(
            track_end(patient_identity),
            track_end(RECEPTIONIST_IDENTITY),
        )

        if total_samples <= 0:
            print(
                "WARNING: Recording contains no usable audio."
            )
            return None

        patient_audio = self._build_participant_audio(
            patient_identity,
            total_samples,
        )

        receptionist_audio = self._build_participant_audio(
            RECEPTIONIST_IDENTITY,
            total_samples,
        )

        # --------------------------------------------------
        # AUDIO VALIDATION
        # --------------------------------------------------

        patient_stats = analyze_audio(patient_audio)
        receptionist_stats = analyze_audio(
            receptionist_audio
        )

        both_sides_active = (
            patient_stats["has_audio_activity"]
            and receptionist_stats["has_audio_activity"]
        )

        self.recording_report = {
            "room_name": self.room_name,
            "output_name": self.output_name,
            "sample_rate": SAMPLE_RATE,
            "channels": {
                "left": "AI patient",
                "right": "Receptionist",
            },
            "participant_identities": {
                "patient": patient_identity,
                "receptionist": RECEPTIONIST_IDENTITY,
            },
            "patient_audio": patient_stats,
            "receptionist_audio": receptionist_stats,
            "both_sides_have_audio_activity": (
                both_sides_active
            ),
            "requires_manual_review": True,
        }

        # --------------------------------------------------
        # PREPARE STEREO AUDIO
        # --------------------------------------------------

        peak = max(
            float(np.max(np.abs(patient_audio))),
            float(np.max(np.abs(receptionist_audio))),
            1.0,
        )

        if peak > 32767.0:
            scale = 32767.0 / peak
            patient_audio *= scale
            receptionist_audio *= scale

        stereo = np.column_stack(
            (
                np.clip(
                    patient_audio,
                    -32768,
                    32767,
                ),
                np.clip(
                    receptionist_audio,
                    -32768,
                    32767,
                ),
            )
        ).astype(np.int16)

        # --------------------------------------------------
        # SAVE WAV
        # --------------------------------------------------

        wav_path = (
            self.output_dir
            / f"{self.output_name}.wav"
        )

        mp3_path = (
            self.output_dir
            / f"{self.output_name}.mp3"
        )

        report_path = (
            self.output_dir
            / f"{self.output_name}_audio_report.json"
        )

        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(stereo.tobytes())

        # --------------------------------------------------
        # SAVE MP3
        # --------------------------------------------------

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(wav_path),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "192k",
                str(mp3_path),
            ],
            check=True,
        )

        # --------------------------------------------------
        # SAVE AUDIO REPORT
        # --------------------------------------------------

        with open(
            report_path,
            "w",
            encoding="utf-8",
        ) as report_file:
            json.dump(
                self.recording_report,
                report_file,
                indent=2,
            )

        # --------------------------------------------------
        # PRINT RESULTS
        # --------------------------------------------------

        print(f"\nRecording saved: {mp3_path}")
        print(f"WAV saved: {wav_path}")
        print(f"Audio report saved: {report_path}")

        print(
            "Audio participants:",
            sorted(self.participants),
        )

        print("Left channel: AI patient")
        print("Right channel: receptionist")

        print("\n=== AUDIO VALIDATION ===")

        print(
            "AI patient:",
            patient_stats,
        )

        print(
            "Receptionist:",
            receptionist_stats,
        )

        if both_sides_active:
            print(
                "PASS: Both sides contain audio activity."
            )
            print(
                "Review the recording to verify "
                "that both sides actually spoke."
            )
        else:
            print(
                "WARNING: One or both sides appear silent."
            )
            print(
                "Do not count this call toward the "
                "assessment until reviewed."
            )

        return mp3_path
