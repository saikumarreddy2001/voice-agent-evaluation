
"""
Speaker-labeled transcription for authorized assessment recordings.

Input:
    Stereo 16-bit WAV recording from recorder.py

Channels:
    LEFT  = AI PATIENT
    RIGHT = RECEPTIONIST

Output:
    <recording_name>_transcript.txt

Uses OpenAI Whisper transcription API.
API usage may incur charges.

Usage:
    python transcribe.py "recordings/example.wav"
"""

import argparse
import asyncio
import os
import tempfile
import wave
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import AsyncOpenAI


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

SPEAKERS = ("AI PATIENT", "RECEPTIONIST")

# Skip channels with no meaningful audio activity.
# These thresholds detect audio, not speech specifically.
SILENCE_PEAK_DBFS = -50.0
SILENCE_RMS_DBFS = -55.0

# Whisper's file upload limit is 25 MB.
# Use smaller chunks for reliable uploads.
MAX_CHUNK_SECONDS = 90
MAX_UPLOAD_BYTES = 24 * 1024 * 1024

TRANSCRIPTION_MODEL = "whisper-1"


# --------------------------------------------------
# AUDIO UTILITIES
# --------------------------------------------------

def audio_dbfs(samples):
    """Return peak and RMS audio levels in dBFS."""

    if samples.size == 0:
        return -120.0, -120.0

    values = samples.astype(np.float64)

    peak = float(np.max(np.abs(values)))
    rms = float(np.sqrt(np.mean(values * values)))

    def convert(value):
        if value <= 0:
            return -120.0
        return float(20 * np.log10(value / 32768.0))

    return convert(peak), convert(rms)


def channel_has_audio(samples):
    """Determine whether a channel contains detectable audio."""

    peak, rms = audio_dbfs(samples)

    return (
        peak >= SILENCE_PEAK_DBFS
        and rms >= SILENCE_RMS_DBFS
    )


def read_stereo_wav(wav_path):
    """Read and validate a stereo PCM WAV file."""

    with wave.open(str(wav_path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        compression = source.getcomptype()

        if channels != 2:
            raise ValueError(
                f"Expected stereo WAV (2 channels), got {channels}."
            )

        if sample_width != 2:
            raise ValueError(
                "Expected 16-bit PCM WAV recording."
            )

        if compression != "NONE":
            raise ValueError(
                "Expected uncompressed PCM WAV recording."
            )

        if sample_rate <= 0:
            raise ValueError("Invalid WAV sample rate.")

        raw_audio = source.readframes(frame_count)

    audio = np.frombuffer(
        raw_audio,
        dtype="<i2",
    ).reshape(-1, 2)

    return sample_rate, audio


def write_mono_wav(path, samples, sample_rate):
    """Write mono 16-bit WAV audio."""

    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(
            np.asarray(samples, dtype="<i2").tobytes()
        )


# --------------------------------------------------
# TRANSCRIPTION
# --------------------------------------------------

async def transcribe_chunk(client, chunk_path):
    """Transcribe one mono WAV chunk with segment timestamps."""

    with open(chunk_path, "rb") as audio_file:
        result = await client.audio.transcriptions.create(
            model=TRANSCRIPTION_MODEL,
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = getattr(result, "segments", None) or []

    output = []

    for segment in segments:
        text = str(
            getattr(segment, "text", "") or ""
        ).strip()

        if not text:
            continue

        start = float(getattr(segment, "start", 0.0))
        end = float(getattr(segment, "end", start))

        output.append(
            (max(0.0, start), max(start, end), text)
        )

    return output


async def transcribe_channel(
    client,
    samples,
    sample_rate,
    speaker,
    temporary_dir,
):
    """Transcribe one speaker channel in sequential chunks."""

    peak, rms = audio_dbfs(samples)

    print(
        f"{speaker}: peak={peak:.1f} dBFS, "
        f"RMS={rms:.1f} dBFS"
    )

    if not channel_has_audio(samples):
        print(
            f"WARNING: {speaker} channel appears silent. "
            "Skipping transcription API request."
        )
        return [], False

    # Bound chunks by duration and upload size.
    bytes_per_sample = 2
    max_samples_by_size = (
        MAX_UPLOAD_BYTES - 44
    ) // bytes_per_sample

    chunk_samples = min(
        int(sample_rate * MAX_CHUNK_SECONDS),
        max_samples_by_size,
    )

    if chunk_samples <= 0:
        raise ValueError("Invalid chunk size.")

    all_segments = []

    for chunk_index, start_sample in enumerate(
        range(0, len(samples), chunk_samples),
        start=1,
    ):
        end_sample = min(
            start_sample + chunk_samples,
            len(samples),
        )

        chunk = samples[start_sample:end_sample]

        # Skip silent chunks to reduce unnecessary API usage.
        if not channel_has_audio(chunk):
            continue

        offset_seconds = start_sample / sample_rate

        chunk_path = (
            Path(temporary_dir)
            / f"{speaker.lower().replace(' ', '_')}_{chunk_index}.wav"
        )

        write_mono_wav(
            chunk_path,
            chunk,
            sample_rate,
        )

        try:
            print(
                f"Transcribing {speaker}, "
                f"chunk {chunk_index}..."
            )

            segments = await transcribe_chunk(
                client,
                chunk_path,
            )

            for start, end, text in segments:
                all_segments.append(
                    (
                        offset_seconds + start,
                        offset_seconds + end,
                        text,
                    )
                )

        finally:
            chunk_path.unlink(missing_ok=True)

    return all_segments, True


# --------------------------------------------------
# GENERATE COMPLETE TRANSCRIPT
# --------------------------------------------------

async def generate_transcript(wav_path):
    """Generate a chronological speaker-labeled transcript."""

    wav_path = Path(wav_path).resolve()

    if not wav_path.is_file():
        raise FileNotFoundError(wav_path)

    sample_rate, stereo_audio = read_stereo_wav(wav_path)

    if stereo_audio.size == 0:
        raise ValueError("Recording contains no audio samples.")

    duration = len(stereo_audio) / sample_rate

    print("\n=== TRANSCRIPTION ===")
    print(f"Recording: {wav_path.name}")
    print(f"Duration: {duration:.1f} seconds")
    print("Left: AI PATIENT")
    print("Right: RECEPTIONIST")

    transcript_path = wav_path.with_name(
        f"{wav_path.stem}_transcript.txt"
    )

    patient_audio = stereo_audio[:, 0].copy()
    receptionist_audio = stereo_audio[:, 1].copy()

    # Do not initialize the API client if both channels
    # appear silent.
    patient_active = channel_has_audio(patient_audio)
    receptionist_active = channel_has_audio(
        receptionist_audio
    )

    if not patient_active:
        print("WARNING: AI PATIENT channel appears silent.")

    if not receptionist_active:
        print("WARNING: RECEPTIONIST channel appears silent.")

    results = [([], False), ([], False)]

    if patient_active or receptionist_active:
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError(
                "OPENAI_API_KEY is missing from .env"
            )

        async with AsyncOpenAI() as client:
            with tempfile.TemporaryDirectory(
                prefix="assessment_transcribe_"
            ) as temporary_dir:

                # Process channels independently.
                # Sequential processing avoids overlapping
                # API requests and simplifies debugging.
                if patient_active:
                    results[0] = await transcribe_channel(
                        client,
                        patient_audio,
                        sample_rate,
                        SPEAKERS[0],
                        temporary_dir,
                    )

                if receptionist_active:
                    results[1] = await transcribe_channel(
                        client,
                        receptionist_audio,
                        sample_rate,
                        SPEAKERS[1],
                        temporary_dir,
                    )

    combined = []

    for speaker, (segments, _) in zip(
        SPEAKERS,
        results,
    ):
        for start, end, text in segments:
            combined.append(
                (start, end, speaker, text)
            )

    combined.sort(
        key=lambda item: (item[0], item[1])
    )

    # --------------------------------------------------
    # SAVE TRANSCRIPT
    # --------------------------------------------------

    with open(
        transcript_path,
        "w",
        encoding="utf-8",
    ) as output:
        output.write(
            f"Recording: {wav_path.name}\n"
        )
        output.write(
            f"Duration: {duration:.2f} seconds\n"
        )
        output.write(
            "Automated transcript; verify against audio.\n"
        )
        output.write(
            "AI PATIENT = left audio channel\n"
        )
        output.write(
            "RECEPTIONIST = right audio channel\n\n"
        )

        if not patient_active:
            output.write(
                "WARNING: AI PATIENT audio channel "
                "appears silent.\n"
            )

        if not receptionist_active:
            output.write(
                "WARNING: RECEPTIONIST audio channel "
                "appears silent.\n"
            )

        if not patient_active or not receptionist_active:
            output.write("\n")

        if combined:
            for start, end, speaker, text in combined:
                output.write(
                    f"[{start:07.2f} - {end:07.2f}] "
                    f"{speaker}: {text}\n"
                )
        else:
            output.write(
                "No transcribed speech segments available.\n"
            )

    print(f"\nTranscript saved: {transcript_path}")

    if patient_active and receptionist_active:
        print(
            "Both audio channels contain activity. "
            "Verify the dialogue manually."
        )
    else:
        print(
            "WARNING: This recording may not qualify "
            "as a complete two-sided conversation."
        )

    return transcript_path


# --------------------------------------------------
# COMMAND LINE
# --------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Generate a speaker-labeled transcript "
            "from a stereo assessment recording."
        )
    )

    parser.add_argument(
        "wav_file",
        help="Path to the stereo WAV recording",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            generate_transcript(args.wav_file)
        )

    except KeyboardInterrupt:
        print("\nTranscription cancelled.")

    except Exception as exc:
        print(f"TRANSCRIPTION ERROR: {exc}")
        raise
