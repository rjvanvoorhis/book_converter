import dataclasses

from book_converter.features.ebook_export import dto, use_cases
from book_converter.presentation import cli


@dataclasses.dataclass(frozen=True)
class ExportEbookCommand:
    use_cases_by_source: dict[str, use_cases.ExportEbookUseCase]

    @property
    def name(self) -> str:
        return "export-ebook"

    @property
    def description(self) -> str:
        return (
            "Write a work as an ebook file (epub, azw3, mobi, pdf, ...) from an "
            "ebook file, an AO3 work/series, a FanFiction.net story or an "
            "extracted-text folder (--source file|ao3|ffnet|extracted)."
        )

    def execute(
        self,
        identifier: str,
        target: str,
        source: str = "file",
        format: str = "epub",
    ) -> str:
        try:
            use_case = self.use_cases_by_source[source]
        except KeyError:
            available = ", ".join(sorted(self.use_cases_by_source))
            raise ValueError(
                f"Unknown source '{source}'. Available: {available}"
            ) from None
        output = use_case.execute(
            dto.ExportEbookInput(identifier=identifier, target=target, format=format)
        )
        lines = []
        if output.collection is not None:
            lines.append(f"Series '{output.collection}': {len(output.ebooks)} ebooks")
        for ebook in output.ebooks:
            origin = "downloaded" if ebook.native else "built"
            lines.append(f"Wrote {output.format} ({origin}) to {ebook.path}")
        return "\n".join(lines)


def build_commands(
    export_by_source: dict[str, use_cases.ExportEbookUseCase],
) -> list[cli.Command]:
    return [ExportEbookCommand(use_cases_by_source=export_by_source)]
