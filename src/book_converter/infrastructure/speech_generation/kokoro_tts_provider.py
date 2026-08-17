import dataclasses
import io

import requests

from book_converter.features.speech_generation import entities
from book_converter.infrastructure.speech_generation import ffmpeg_support


@dataclasses.dataclass(frozen=True)
class KokoroTtsProvider:
    base_url: str = "http://localhost:8880"
    response_format: str = "wav"
    timeout: float = 300.0

    def get_engine_profiles(self) -> list[entities.EngineProfile]:
        return [entities.EngineProfile(id="kokoro", description="Local Kokoro TTS engine")]

    def get_voice_profiles(self, engine: entities.EngineId) -> list[entities.VoiceProfile]:
        response = requests.get(f"{self.base_url}/v1/audio/voices", timeout=self.timeout)
        response.raise_for_status()
        return [
            entities.VoiceProfile(id=entities.VoiceId(voice["id"]), description=voice.get("name"))
            for voice in response.json()["voices"]
        ]

    def generate(
        self, text: str, engine: entities.EngineId, voice: entities.VoiceId
    ) -> entities.SpeechResult:
        response = requests.post(
            f"{self.base_url}/v1/audio/speech",
            json={
                "model": engine,
                "input": text,
                "voice": voice,
                "response_format": self.response_format,
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        audio = response.content
        duration = round(ffmpeg_support.probe_duration_seconds_from_bytes(audio))
        return entities.SpeechResult(data=io.BytesIO(audio), duration=duration)
