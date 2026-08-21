import dataclasses
import re
import typing


@dataclasses.dataclass
class PronunciationEntry:
    """Represents a single pronunciation entry.
    
    Attributes:
        value: The pronunciation value (IPA, phonetic spelling, etc.)
        method: The method to apply - "ipa" formats as [Word](/value/),
               "spelling" just replaces the word with value.
    """
    value: str
    method: str = "ipa"


@dataclasses.dataclass
class PronunciationTextAnnotator:
    pronunciations: dict[str, typing.Any]

    def __post_init__(self) -> None:
        # Parse pronunciations into a normalized format
        self._pronunciations_parsed: dict[str, PronunciationEntry] = {}
        
        for word, pronunciation in self.pronunciations.items():
            if isinstance(pronunciation, dict):
                # New format: {"value": "...", "method": "..."}
                self._pronunciations_parsed[word.lower()] = PronunciationEntry(
                    value=pronunciation.get("value", ""),
                    method=pronunciation.get("method", "ipa"),
                )
            else:
                # Legacy format: just a string (default to IPA method)
                self._pronunciations_parsed[word.lower()] = PronunciationEntry(
                    value=pronunciation,
                    method="ipa",
                )
        
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
        entry = self._pronunciations_parsed[word.lower()]
        
        if entry.method == "ipa":
            return f"[{word}](/{entry.value}/)"
        elif entry.method == "spelling":
            return entry.value
        else:
            raise ValueError(f"Unknown pronunciation method: {entry.method}")
