import dataclasses

import requests

_SYSTEM_PROMPT = (
    "You are a careful copyeditor for fiction. Fix only clear typos, spelling "
    "mistakes, and grammatical errors (e.g. wrong word forms like 'you'/'your', "
    "'their'/'there'/'they're', subject-verb agreement, missing punctuation). "
    "Do not rephrase, rewrite, summarize, or change wording, tone, or style. "
    "Preserve the author's voice, sentence structure, dialogue, formatting, and "
    "any intentional fragments or unusual phrasing exactly as written if they "
    "are not actual errors. Respond with ONLY the corrected text and nothing "
    "else - no commentary, no explanations, no quotation marks, no markdown."
)


@dataclasses.dataclass(frozen=True)
class LmStudioCopyEditor:
    base_url: str = "http://localhost:1234/v1"
    model: str = "local-model"
    timeout: float = 120.0

    def edit(self, text: str) -> str:
        paragraphs = text.split("\n\n")
        return "\n\n".join(
            self._edit_paragraph(paragraph) if paragraph.strip() else paragraph
            for paragraph in paragraphs
        )

    def _edit_paragraph(self, paragraph: str) -> str:
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": paragraph},
                ],
                "temperature": 0,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = _strip_wrapping(
            response.json()["choices"][0]["message"]["content"].strip()
        )

        if not content or len(content) < len(paragraph) * 0.5:
            return paragraph
        return content


def _strip_wrapping(text: str) -> str:
    if text.startswith("```") and text.endswith("```"):
        text = text.removeprefix("```").removesuffix("```").strip()
        first_line, _, rest = text.partition("\n")
        if rest and len(first_line.split()) <= 1:
            text = rest.strip()

    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1]

    return text.strip()
