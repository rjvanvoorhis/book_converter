import dataclasses
import io

import requests


from book_converter.features.speech_generation import entities
from book_converter.infrastructure.speech_generation import ffmpeg_support


@dataclasses.dataclass(frozen=True)
class PocketTtsProvider:
    base_url: str = "http://localhost:8000"
    timeout: float = 10_000.0

    def get_engine_profiles(self) -> list[entities.EngineProfile]:
        return [
            entities.EngineProfile(
                id="pocket-tts", description="Local Pocket TTS engine"
            )
        ]

    @staticmethod
    def _record_to_key(record: dict):
        return record["name"].lower()

    def _get_name_map(self):
        response = requests.get(f"{self.base_url}/voices")
        response.raise_for_status()
        return {self._record_to_key(record): record for record in response.json()}

    def get_voice_profiles(
        self, engine: entities.EngineId
    ) -> list[entities.VoiceProfile]:
        name_map = self._get_name_map()
        return [
            entities.VoiceProfile(
                id=entities.VoiceId(id), description=record.get("name")
            )
            for id, record in name_map.items()
        ]

    def generate(
        self, text: str, engine: entities.EngineId, voice: entities.VoiceId
    ) -> entities.SpeechResult:
        name_map = self._get_name_map()
        voice_record = name_map[voice]
        voice_url = f"{self.base_url}/voices/{voice_record['id']}/data"
        data = io.BytesIO()
        with requests.post(
            f"{self.base_url}/tts",
            data={"text": text, "voice_url": voice_url},
            timeout=self.timeout,
            stream=True,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    data.write(chunk)
        data.seek(0)
        # TODO: fix this
        duration = 0
        return entities.SpeechResult(data=data, duration=duration)
