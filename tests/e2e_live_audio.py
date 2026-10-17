"""Generate fake-microphone WAVs for the live E2E suite (tests/e2e-live.spec.ts).

Azure TTS REST with Entra ID (DefaultAzureCredential → Speech STS token), 16 kHz
mono PCM16, padded with silence so Chromium's
``--use-file-for-fake-audio-capture`` loop contains one clear question.

Usage: python tests/e2e_live_audio.py <out_dir>
"""
from __future__ import annotations

import io
import os
import sys
import wave
from pathlib import Path
from xml.sax.saxutils import escape

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "demos" / "backend" / ".env", override=True)

QUESTIONS = {
    "question-en.wav": ("en-US", "en-US-AndrewNeural", "Hello, I have a question about this presentation. What makes an agent different from a plain model?"),
}

LEAD_S = 0.5
# Lead + tail silence stay under the capture's 5 s initial-silence cutoff; the
# preamble absorbs a capture that starts mid-file (the fake mic loops).
TAIL_S = 3.5


def _speech_token(endpoint: str) -> str:
    aad = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default").token
    r = requests.post(f"{endpoint.rstrip('/')}/sts/v1.0/issuetoken",
                      headers={"Authorization": f"Bearer {aad}", "Content-Length": "0"}, timeout=20)
    r.raise_for_status()
    return r.text


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    endpoint = os.environ["AZURE_SPEECH_ENDPOINT"]
    region = os.environ.get("AZURE_SPEECH_REGION", "swedencentral")
    token = _speech_token(endpoint)
    for name, (lang, voice, text) in QUESTIONS.items():
        ssml = (f"<speak version='1.0' xml:lang='{lang}'><voice name='{voice}'>"
                f"{escape(text)}</voice></speak>")
        r = requests.post(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/ssml+xml",
                     "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm", "User-Agent": "oz-radio-e2e"},
            data=ssml.encode("utf-8"), timeout=30)
        r.raise_for_status()
        with wave.open(io.BytesIO(r.content)) as w:
            pcm = w.readframes(w.getnframes())
            rate = w.getframerate()
        silence = lambda s: b"\x00\x00" * int(rate * s)  # noqa: E731
        with wave.open(str(out / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(silence(LEAD_S) + pcm + silence(TAIL_S))
        print(f"{name}: {len(pcm) / 2 / rate:.2f}s speech, {lang}")


if __name__ == "__main__":
    main()
