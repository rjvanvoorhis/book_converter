import dataclasses
import re

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n+")


@dataclasses.dataclass(frozen=True)
class PauseTextAnnotator:
    seconds: float = 0.6

    def annotate(self, text: str) -> str:
        return _PARAGRAPH_BREAK.sub(f" [pause:{self.seconds}s] ", text)
