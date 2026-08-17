import dataclasses
import re


@dataclasses.dataclass
class PronunciationTextAnnotator:
    pronunciations: dict[str, str]

    def __post_init__(self) -> None:
        self._lookup = {word.lower(): ipa for word, ipa in self.pronunciations.items()}
        self._pattern = (
            re.compile(
                r"\b(?:" + "|".join(re.escape(word) for word in self.pronunciations) + r")\b",
                re.IGNORECASE,
            )
            if self.pronunciations
            else None
        )

    def annotate(self, text: str) -> str:
        if self._pattern is None:
            return text
        return self._pattern.sub(self._replace, text)

    def _replace(self, match: re.Match[str]) -> str:
        word = match.group(0)
        ipa = self._lookup[word.lower()]
        return f"[{word}](/{ipa}/)"
