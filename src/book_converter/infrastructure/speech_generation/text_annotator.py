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
