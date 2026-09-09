from book_converter.infrastructure.speech_generation import ffmpeg_support


class FfmpegAudioCleaner:
    """Denoises a clip with ffmpeg's own filters - a high-pass to cut rumble
    plus an FFT-based spectral-gate denoiser (afftdn). Zero extra
    dependencies (ffmpeg is already a hard requirement of this project) and
    fast, but a simpler/older technique than a model-based cleaner - see
    resemble_enhance_audio_cleaner.ResembleEnhanceAudioCleaner for a
    higher-fidelity alternative."""

    id = "ffmpeg"
    description = "Fast, always available (highpass + spectral-gate denoise)"

    def __init__(self, denoise_amount: float = 25.0) -> None:
        self._denoise_amount = denoise_amount

    def clean(self, wav_bytes: bytes) -> bytes:
        filters = ["highpass=f=80"]
        if self._denoise_amount > 0:
            filters.append(f"afftdn=nf=-{self._denoise_amount}")
        return ffmpeg_support.apply_audio_filters(wav_bytes, filters)
