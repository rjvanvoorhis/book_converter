import dataclasses
import json

from book_converter.features.speech_generation import interfaces
from book_converter.infrastructure.speech_generation import pause_text_annotator
from book_converter.infrastructure.speech_generation import pronunciation_text_annotator


class PassthroughTextAnnotator:
    def annotate(self, text: str) -> str:
        return text


@dataclasses.dataclass(frozen=True)
class CompositeTextAnnotator:
    annotators: list[interfaces.TextAnnotator]

    def annotate(self, text: str) -> str:
        for annotator in self.annotators:
            text = annotator.annotate(text)
        return text


def build_from_pronunciations_file(pronunciations_path: str) -> CompositeTextAnnotator:
    with open(pronunciations_path, encoding="utf-8") as f:
        pronunciations = json.load(f)

    return CompositeTextAnnotator(
        annotators=[
            pronunciation_text_annotator.PronunciationTextAnnotator(
                pronunciations=pronunciations
            ),
            pause_text_annotator.PauseTextAnnotator(),
        ]
    )


def build_text_annotator(
    pronunciations_path: str | None = None,
    add_pauses: bool = False,
) -> interfaces.TextAnnotator:
    """Build a text annotator based on optional configurations.

    Args:
        pronunciations_path: Path to a JSON file with pronunciation dictionary.
                           If None, pronunciation annotation is disabled.
        add_pauses: If True, enable pause annotations.

    Returns:
        A TextAnnotator (PassthroughTextAnnotator if no annotators, CompositeTextAnnotator otherwise).
    """
    annotators: list[interfaces.TextAnnotator] = []

    if pronunciations_path is not None:
        with open(pronunciations_path, encoding="utf-8") as f:
            pronunciations = json.load(f)
        annotators.append(
            pronunciation_text_annotator.PronunciationTextAnnotator(
                pronunciations=pronunciations
            )
        )

    if add_pauses:
        annotators.append(pause_text_annotator.PauseTextAnnotator())

    if not annotators:
        return PassthroughTextAnnotator()

    return CompositeTextAnnotator(annotators=annotators)
