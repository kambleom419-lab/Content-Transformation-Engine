from engine.ingestion.chunking import split_paragraphs
from engine.ingestion.types import SourceBlock


def parse_text(text: str, name: str) -> list[SourceBlock]:
    return [
        SourceBlock(text=para, ref=f"{name} §{i}", kind="paragraph")
        for i, para in enumerate(split_paragraphs(text or ""), start=1)
    ]
