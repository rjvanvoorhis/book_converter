import dataclasses
import re

from book_converter.features.speech_generation import entities

# Matches straight ("...") and curly (“...”) double quotes. HTML-sourced text
# (AO3/epub) is normalized to straight quotes by html_text.normalize_text
# before it reaches here, but the "extracted" book source reads pre-existing
# plain text directly and skips that step, so curly quotes can still show up.
_QUOTE_SPAN = re.compile(r'["“][^"”]*["”]')


@dataclasses.dataclass(frozen=True)
class QuoteDialogueSegmenter:
    """Splits chapter text into narration/dialogue runs at paragraph granularity.

    A paragraph containing any quoted span is voiced entirely in the dialogue
    voice - attribution tags and action beats ('he said, shrugging') included.
    Switching narrator/dialogue voice mid-sentence for a three-word attribution
    tag reads as jarring back-and-forth; a paragraph is the smallest unit a
    voice switch happens at. Only a paragraph with no quotes at all is treated
    as narration.

    Doesn't attempt to identify *who* is speaking - every dialogue paragraph is
    tagged with entities.UNKNOWN_SPEAKER. A future attribution pass can replace
    this segmenter without touching the rest of the pipeline, since both
    produce/consume the same DialogueSegment shape.
    """

    def segment(self, text: str) -> list[entities.DialogueSegment]:
        segments: list[entities.DialogueSegment] = []
        for paragraph in text.split("\n\n"):
            stripped = paragraph.strip()
            if stripped:
                speaker = entities.UNKNOWN_SPEAKER if _QUOTE_SPAN.search(stripped) else None
                segments.append(entities.DialogueSegment(text=stripped, speaker=speaker))
        return _merge_adjacent_narration(segments)


def _merge_adjacent_narration(
    segments: list[entities.DialogueSegment],
) -> list[entities.DialogueSegment]:
    merged: list[entities.DialogueSegment] = []
    for segment in segments:
        if segment.speaker is None and merged and merged[-1].speaker is None:
            merged[-1] = entities.DialogueSegment(
                text=f"{merged[-1].text}\n\n{segment.text}", speaker=None
            )
        else:
            merged.append(segment)
    return merged
