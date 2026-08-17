import dataclasses

from book_converter.features.speech_generation import interfaces


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
