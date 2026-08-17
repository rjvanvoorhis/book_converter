import language_tool_python


class LanguageToolCopyEditor:
    def __init__(self, language: str = "en-US") -> None:
        self._language = language
        self._tool: language_tool_python.LanguageTool | None = None

    def edit(self, text: str) -> str:
        return self._get_tool().correct(text)

    def close(self) -> None:
        if self._tool is not None:
            self._tool.close()
            self._tool = None

    def _get_tool(self) -> language_tool_python.LanguageTool:
        if self._tool is None:
            self._tool = language_tool_python.LanguageTool(self._language)
        return self._tool
