import dataclasses
import io
import wave

import numpy as np

# Originally tuned against one confirmed pocket-tts failure, then validated
# against a full 8.5-hour audiobook: a short input segment that, instead of
# ending cleanly, devolves into several seconds of noise before the model
# finally stops - starting as loud broadband noise, then decaying into a
# quieter tonal murk that isn't silence but isn't real speech either.
#
# Detection is three-stage:
#
# - *Trigger* on amplitude: real speech almost always has some near-silent
#   dip within any 1-second window (a stop consonant, a breath, a word
#   boundary); the confirmed artifact's loud broadband core showed zero such
#   dips for 6.6 straight seconds. But amplitude alone isn't precise enough
#   to act on - scanning a full audiobook with only this trigger produced 543
#   candidates in 8.5 hours, most of them sustained loud/emphatic speech
#   (shouting, emphatic dialogue) that also happens not to dip in a given
#   window. So this stage is over-sensitive on purpose, to avoid missing
#   anything, and stage two cleans up after it.
# - *Confirm* on spectral centroid stability: real speech's pitch/timbre
#   center is always moving (formants, prosody) even when it's loud and
#   amplitude-flat; this artifact's centroid stays locked in place whether
#   it's loud or quiet. Requiring both the median *and* the 75th-percentile
#   local centroid stability within a candidate span to stay low cut the
#   full-book candidate count from 543 to 46, and spot-checking a sample of
#   those 46 across the book (different volumes, different chapters) showed
#   the same loud-broadband-then-murky-tail signature every time - this
#   stage is doing the real precision work.
# - *Extend* the confirmed span using the same centroid signal, since the
#   quieter tail isn't loud-flat (amplitude can't see it) but is still
#   centroid-flat.
#
# These thresholds are tuned from one audiobook, not a general theory of
# speech - watch the warning logs as more of the corpus gets regenerated.
_FRAME_SECONDS = 0.02
_WINDOW_SECONDS = 1.0
_DROP_BELOW_PEAK_DB = 30.0
_NEAR_SILENCE_RATIO_THRESHOLD = 0.02
_MIN_ARTIFACT_SECONDS = 1.5
_REPLACEMENT_GAP_SECONDS = 0.3
_FADE_SECONDS = 0.01

_CENTROID_FFT_SECONDS = 2048 / 24000
_LOCAL_STABILITY_SECONDS = 0.3
_CONFIRM_CENTROID_STD_MEDIAN_HZ = 150.0
_CONFIRM_CENTROID_STD_P75_HZ = 150.0
_EXTEND_CLEAR_STD_HZ = 300.0
_EXTEND_CONFIRM_SECONDS = 0.5

# Even after the centroid-stability gate above, a full-book run against 45
# user-labeled candidates (27 real, 18 ordinary pauses misfiring the
# amplitude trigger) showed the centroid gate alone wasn't enough: ordinary
# ambient/room-tone during ordinary pauses can also look "centroid-flat".
# What actually separated the two groups was core (pre-extension) span
# duration: every mislabeled pause topped out at 3.02s, while all but 3 of
# the real artifacts ran 3.66s or longer - a clean 0.6s gap between the two
# groups. The 3 short real artifacts that duration alone would miss all had
# a dramatically lower centroid median (<50Hz, vs a pause's 70-125Hz), so
# that's kept as a fallback for the short-but-unambiguous case.
_CONFIRM_MIN_DURATION_SECONDS = 3.2
_CONFIRM_STRONG_CENTROID_STD_HZ = 50.0


@dataclasses.dataclass(frozen=True)
class ArtifactCut:
    """A span of detected noise artifact, in seconds relative to the
    original (pre-splice) audio."""

    start_seconds: float
    end_seconds: float


def find_artifacts(wav_bytes: bytes) -> list[ArtifactCut]:
    """Detect artifact spans without doing the splice/fade pass - for a
    caller (e.g. an audit scan) that only needs the cut locations, not the
    modified audio. `wav_bytes` is expected to be a short-ish clip (see
    `_find_artifact_spans`'s per-frame arrays): scan a long file in chunks
    and call this per chunk rather than passing a whole multi-hour file."""
    _, cuts = strip_noise_artifacts(wav_bytes)
    return cuts


def strip_noise_artifacts(wav_bytes: bytes) -> tuple[bytes, list[ArtifactCut]]:
    """Detect and splice out sustained-noise artifacts from pocket-tts output.

    Retrying generation isn't reliable here since nothing guarantees the same
    text won't fail the same way again. Instead, each detected artifact span
    is cut out and replaced with a short silence, deterministically removing
    the noise at the cost of a small gap where those seconds of audio used to
    be.

    Returns the (possibly modified) WAV bytes and the list of cuts made, so
    callers can log what happened.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as reader:
        params = reader.getparams()
        raw = reader.readframes(reader.getnframes())

    if params.sampwidth != 2 or params.nchannels != 1:
        # Only handles the mono 16-bit PCM pocket-tts always returns; pass
        # through unmodified rather than risk misinterpreting samples.
        return wav_bytes, []

    samples = np.frombuffer(raw, dtype=np.int16)
    cuts = _find_artifact_spans(samples, params.framerate)
    if not cuts:
        return wav_bytes, []

    filtered = _splice_out(samples, params.framerate, cuts)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(params.nchannels)
        writer.setsampwidth(params.sampwidth)
        writer.setframerate(params.framerate)
        writer.writeframes(filtered.tobytes())
    return buffer.getvalue(), cuts


def _find_artifact_spans(samples: np.ndarray, sample_rate: int) -> list[ArtifactCut]:
    frame_len = max(1, int(sample_rate * _FRAME_SECONDS))
    n_frames = len(samples) // frame_len
    if n_frames == 0:
        return []

    frames = samples[: n_frames * frame_len].astype(np.float64).reshape(n_frames, -1)
    rms = np.sqrt(np.mean(frames**2, axis=1)) + 1.0
    db = 20 * np.log10(rms)

    window_frames = max(1, int(_WINDOW_SECONDS / _FRAME_SECONDS))
    near_silence_ratio = _rolling_near_silence_ratio(db, window_frames)
    is_core_artifact = near_silence_ratio <= _NEAR_SILENCE_RATIO_THRESHOLD
    min_artifact_frames = int(_MIN_ARTIFACT_SECONDS / _FRAME_SECONDS)

    core_spans: list[tuple[int, int]] = []
    start = None
    for i, flagged in enumerate(is_core_artifact):
        if flagged and start is None:
            start = i
        elif not flagged and start is not None:
            if i - start >= min_artifact_frames:
                core_spans.append((start, i))
            start = None
    if start is not None and n_frames - start >= min_artifact_frames:
        core_spans.append((start, n_frames))

    if not core_spans:
        return []

    centroid = _spectral_centroid_track(samples, sample_rate, frame_len)
    local_window = max(1, int(_LOCAL_STABILITY_SECONDS / _FRAME_SECONDS))
    local_std = _rolling_std(centroid, local_window)

    confirmed_spans = [
        (start, end)
        for start, end in core_spans
        if np.median(local_std[start:end]) < _CONFIRM_CENTROID_STD_MEDIAN_HZ
        and np.percentile(local_std[start:end], 75) < _CONFIRM_CENTROID_STD_P75_HZ
        and (
            (end - start) * _FRAME_SECONDS >= _CONFIRM_MIN_DURATION_SECONDS
            or np.median(local_std[start:end]) < _CONFIRM_STRONG_CENTROID_STD_HZ
        )
    ]
    if not confirmed_spans:
        return []

    is_clearly_speech = local_std >= _EXTEND_CLEAR_STD_HZ
    confirm_frames = max(1, int(_EXTEND_CONFIRM_SECONDS / _FRAME_SECONDS))

    extended_spans = [
        (start, _first_sustained_true(is_clearly_speech, end, confirm_frames))
        for start, end in confirmed_spans
    ]

    return [
        ArtifactCut(start_seconds=start * _FRAME_SECONDS, end_seconds=end * _FRAME_SECONDS)
        for start, end in extended_spans
    ]


def _rolling_near_silence_ratio(db: np.ndarray, window_frames: int) -> np.ndarray:
    """For each frame, the fraction of frames in a centered `window_frames`
    window that fall more than `_DROP_BELOW_PEAK_DB` below that window's own
    peak. Real speech's natural pauses keep this well above zero almost
    everywhere; sustained noise holds it at zero."""
    n = len(db)
    half = window_frames // 2
    ratio = np.empty(n)
    for i in range(n):
        local = db[max(0, i - half) : min(n, i + half)]
        ratio[i] = np.mean(local < (local.max() - _DROP_BELOW_PEAK_DB))
    return ratio


def _spectral_centroid_track(
    samples: np.ndarray, sample_rate: int, frame_len: int
) -> np.ndarray:
    """Spectral centroid (power-weighted mean frequency) of a window centered
    on each `frame_len`-spaced frame. Uses a wider FFT window than the frame
    spacing for enough frequency resolution to track real pitch/timbre
    movement rather than bin-hopping noise."""
    n_frames = len(samples) // frame_len
    fft_len = max(frame_len, int(sample_rate * _CENTROID_FFT_SECONDS))
    half = fft_len // 2

    padded = np.zeros(len(samples) + 2 * (half + fft_len), dtype=np.float64)
    padded[half + fft_len : half + fft_len + len(samples)] = samples
    window = np.hanning(fft_len)
    freqs = np.fft.rfftfreq(fft_len, d=1.0 / sample_rate)

    centers = np.arange(n_frames) * frame_len + frame_len // 2 + half + fft_len
    starts = centers - half
    windows = np.lib.stride_tricks.sliding_window_view(padded, fft_len)[starts] * window

    power = np.abs(np.fft.rfft(windows, axis=1)) ** 2
    return (power @ freqs) / (power.sum(axis=1) + 1e-9)


def _rolling_std(x: np.ndarray, window_frames: int) -> np.ndarray:
    n = len(x)
    half = window_frames // 2
    out = np.empty(n)
    for i in range(n):
        out[i] = np.std(x[max(0, i - half) : min(n, i + half)])
    return out


def _first_sustained_true(mask: np.ndarray, from_index: int, run_frames: int) -> int:
    """First index at/after `from_index` where a run of `run_frames`
    consecutive True values in `mask` begins, or the end of the array if no
    such run occurs."""
    n = len(mask)
    if from_index >= n:
        return n
    cumulative = np.concatenate([[0], np.cumsum(mask.astype(int))])
    for j in range(from_index, n - run_frames + 1):
        if cumulative[j + run_frames] - cumulative[j] == run_frames:
            return j
    return n


def _splice_out(
    samples: np.ndarray, sample_rate: int, cuts: list[ArtifactCut]
) -> np.ndarray:
    fade_len = int(_FADE_SECONDS * sample_rate)
    gap = np.zeros(int(_REPLACEMENT_GAP_SECONDS * sample_rate), dtype=np.int16)
    pieces = []
    cursor = 0
    for index, cut in enumerate(cuts):
        start_sample = int(cut.start_seconds * sample_rate)
        end_sample = int(cut.end_seconds * sample_rate)
        piece = samples[cursor:start_sample]
        if index > 0:
            # This piece's start immediately follows the previous cut's gap.
            piece = _fade_in(piece, fade_len)
        pieces.append(_fade_out(piece, fade_len))
        pieces.append(gap)
        cursor = end_sample

    tail = samples[cursor:]
    if cuts:
        tail = _fade_in(tail, fade_len)
    pieces.append(tail)
    return np.concatenate(pieces)


def _fade_out(segment: np.ndarray, fade_len: int) -> np.ndarray:
    n = min(fade_len, len(segment))
    if n <= 0:
        return segment
    faded = segment.astype(np.float64)
    faded[-n:] *= np.linspace(1.0, 0.0, n)
    return faded.astype(np.int16)


def _fade_in(segment: np.ndarray, fade_len: int) -> np.ndarray:
    n = min(fade_len, len(segment))
    if n <= 0:
        return segment
    faded = segment.astype(np.float64)
    faded[:n] *= np.linspace(0.0, 1.0, n)
    return faded.astype(np.int16)
