from dataclasses import dataclass, field


@dataclass
class SourceBlock:
    text: str
    ref: str
    kind: str = "paragraph"
    page: int | None = None
    heading: str | None = None
    source_id: str = ""


@dataclass
class IngestedSource:
    source_id: str
    kind: str
    source_type: str
    language: str = "en"
    blocks: list[SourceBlock] = field(default_factory=list)
    title: str | None = None
    meta: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def corpus(self) -> list[dict]:
        return [
            {
                "text": b.text,
                "source_ref": b.ref,
                "kind": b.kind,
                "source_id": b.source_id or self.source_id,
            }
            for b in self.blocks
        ]

    def descriptor(self) -> dict:
        return {
            "source_id": self.source_id,
            "kind": self.kind,
            "source_type": self.source_type,
            "language": self.language,
            "title": self.title,
            "blocks": len(self.blocks),
            "warnings": self.warnings,
        }
