"""
Run the 'understand' step by itself, without the rest of the graph.

Usage:
    # quick smoke test, no API key needed
    python scripts/run_understand.py --provider stub

    # against a text file, using real Gemini
    python scripts/run_understand.py --file path/to/advisory.pdf --provider gemini

    # paste text directly
    python scripts/run_understand.py --text "..." --provider gemini
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.ingestion import ingest_sources
from engine.llm import GeminiAdapter, StubAdapter
from engine.understand import run_understand

SAMPLE_TEXT = """\
Security Advisory: Critical Remote Code Execution in AcmeServer

A critical vulnerability, CVE-2024-31337, has been identified in AcmeServer versions
prior to 4.2.1. The flaw allows unauthenticated remote code execution via a crafted
HTTP request to the /api/upload endpoint. Exploitation has been observed in the wild,
originating from IP address 198.51.100.23 and domain malicious-update[.]net.

Timeline:
- 2024-03-01: Vulnerability privately reported to vendor.
- 2024-03-10: Vendor released patch 4.2.1.
- 2024-03-14: Public exploitation observed.

Affected organisations should patch to version 4.2.1 or later immediately, and block
network traffic to the indicators listed above. A SHA256 hash of the observed malware
sample is d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", help="Path to a source file (PDF, DOCX, TXT, image, etc.)")
    parser.add_argument("--text", help="Raw text to analyse instead of a file")
    parser.add_argument("--provider", choices=["stub", "gemini"], default="stub")
    parser.add_argument("--max-chars-per-batch", type=int, default=9000)
    args = parser.parse_args()

    llm = StubAdapter() if args.provider == "stub" else GeminiAdapter()

    if args.file:
        path = Path(args.file)
        source_input = {"id": path.name, "filename": path.name, "path": str(path)}
    elif args.text:
        source_input = {"id": "pasted-text", "kind": "text", "text": args.text}
    else:
        print("(no --file/--text given, using built-in sample advisory)\n", file=sys.stderr)
        source_input = {"id": "sample-advisory.txt", "kind": "text", "text": SAMPLE_TEXT}

    corpus, descriptors, warnings = ingest_sources([source_input], llm)
    if warnings:
        print("Ingestion warnings:", warnings, file=sys.stderr)
    print(f"Ingested {len(corpus)} chunk(s) from {len(descriptors)} source(s).\n", file=sys.stderr)

    model = run_understand(
        corpus=corpus,
        source_input=source_input,
        sources=descriptors,
        llm=llm,
        max_chars_per_batch=args.max_chars_per_batch,
    )

    print(json.dumps(model, indent=2, ensure_ascii=False))

    meta = model.get("_meta", {})
    print("\n--- summary ---", file=sys.stderr)
    print(f"batches used:        {meta.get('batches')}", file=sys.stderr)
    print(f"retries needed:      {meta.get('retries')}", file=sys.stderr)
    print(f"facts extracted:     {meta.get('facts_extracted')}", file=sys.stderr)
    print(f"facts grounded:      {meta.get('facts_grounded')}", file=sys.stderr)
    print(f"facts dropped:       {meta.get('facts_dropped_ungrounded')}", file=sys.stderr)
    print(f"regex IOCs found:    {meta.get('regex_iocs_found')}", file=sys.stderr)


if __name__ == "__main__":
    main()