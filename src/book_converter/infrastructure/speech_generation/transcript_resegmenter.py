import re

from book_converter.infrastructure.speech_generation import (
    audiobook_library,
    review_store,
)
from book_converter.infrastructure.speech_generation.quote_dialogue_segmenter import (
    _MAX_MERGED_NARRATION_CHARS,
)

# Used only as a fallback for a segment with no "\n\n" at all - a single
# paragraph that's long enough on its own to exceed the cap. Real paragraph
# boundaries (recovered via "\n\n", see _split_units) are preferred whenever
# they're available, since they're the segment's actual original structure
# rather than a guess at sentence punctuation.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def resegment_long_segments(m4b_path: str) -> dict:
    """Split any transcript segment over `_MAX_MERGED_NARRATION_CHARS` back
    into several smaller segments, without touching the underlying audio.

    A merged narration segment's text is exactly its original paragraphs
    joined with "\\n\\n" (that's how quote_dialogue_segmenter built it), so
    splitting on "\\n\\n" recovers the real paragraph boundaries - no need to
    guess at sentence punctuation. Each piece's timing is estimated
    proportionally by character position within the original segment's text,
    scaled across the segment's real [start_seconds, end_seconds) - an
    approximation (assumes ~constant speech rate within one segment's own
    TTS take), but the audio itself is never touched, so a little drift at a
    split point is a minor imprecision rather than a correctness issue.
    """
    transcript = audiobook_library.read_transcript(m4b_path)
    segments = transcript["segments"]

    new_segments: list[dict] = []
    segments_split = 0
    for segment in segments:
        if len(segment["text"]) <= _MAX_MERGED_NARRATION_CHARS:
            new_segments.append(segment)
            continue
        pieces = _split_segment(segment)
        new_segments.append(pieces[0])
        new_segments.extend(pieces[1:])
        if len(pieces) > 1:
            segments_split += 1

    transcript["segments"] = new_segments
    audiobook_library.write_transcript(m4b_path, transcript)
    # Review entries are keyed by segment index, which this operation
    # reshuffles for everything after a split - stale entries would attach
    # to the wrong segment. Detected-artifact cuts are keyed by timestamp
    # instead and no audio moved, so those are left alone.
    review_store.clear_review(m4b_path)

    return {
        "original_segment_count": len(segments),
        "new_segment_count": len(new_segments),
        "segments_split": segments_split,
    }


def _split_segment(segment: dict) -> list[dict]:
    text = segment["text"]
    start_seconds = segment["start_seconds"]
    end_seconds = segment["end_seconds"]
    duration = end_seconds - start_seconds

    pieces = _split_text(text, _MAX_MERGED_NARRATION_CHARS)
    total_chars = pieces[-1][2] if pieces else 0
    if total_chars == 0:
        return [segment]

    result = []
    for piece_text, offset_start, offset_end in pieces:
        piece_start = start_seconds + duration * offset_start / total_chars
        piece_end = start_seconds + duration * offset_end / total_chars
        result.append(
            {
                "chapter_title": segment["chapter_title"],
                "speaker": segment["speaker"],
                "text": piece_text,
                "start_seconds": piece_start,
                "end_seconds": piece_end,
            }
        )
    return result


def _split_text(text: str, max_chars: int) -> list[tuple[str, int, int]]:
    """Greedily group text's paragraphs (or, lacking any, sentences) into
    pieces no longer than `max_chars`, returning each piece alongside its
    [start, end) character offsets in `text` (well, in `separator.join(units)`
    - identical to `text` in the paragraph case, since split/join are exact
    inverses; only approximate in the sentence fallback, where the original
    inter-sentence whitespace isn't preserved verbatim)."""
    if "\n\n" in text:
        units, separator = text.split("\n\n"), "\n\n"
    else:
        units, separator = _SENTENCE_BOUNDARY.split(text), " "

    grouped: list[list[str]] = []
    for unit in units:
        if grouped:
            candidate = grouped[-1] + [unit]
            if len(separator.join(candidate)) <= max_chars:
                grouped[-1] = candidate
                continue
        grouped.append([unit])

    pieces: list[tuple[str, int, int]] = []
    cursor = 0
    for index, group_units in enumerate(grouped):
        if index > 0:
            cursor += len(separator)
        piece_text = separator.join(group_units)
        start = cursor
        cursor += len(piece_text)
        pieces.append((piece_text, start, cursor))
    return pieces
