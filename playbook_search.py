"""
Search tool over the sales enablement docs (playbook, ICP, battlecards,
objection handling, pricing, case studies).

Retrieval approach: split each doc into its "## " sections, score sections by
keyword overlap with the query, return the top matches. With only 7 short
docs (~800 lines total), a full embeddings/vector-store pipeline isn't
justified — keyword scoring over section-sized chunks is simple, fast, and
easy to reason about. Would move to embeddings if the corpus grew materially.
"""

import re
from pathlib import Path

ENABLEMENT_DIR = Path(__file__).resolve().parent / "data" / "enablement"

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "and", "or", "but", "of",
    "to", "in", "on", "for", "with", "what", "how", "does", "do", "we",
    "our", "their", "them", "it", "this", "that", "at", "as", "by", "be",
    "about", "vs", "against",
}


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return [w for w in words if w not in _STOPWORDS]


def _load_chunks() -> list[dict]:
    chunks = []
    for path in sorted(ENABLEMENT_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else path.stem

        sections = re.split(r"^##\s+", text, flags=re.MULTILINE)
        # sections[0] is the doc preamble before the first "## " heading.
        preamble = sections[0]
        if preamble.strip():
            chunks.append({"doc": doc_title, "source": path.name, "section": doc_title, "text": preamble.strip()})
        for section in sections[1:]:
            lines = section.split("\n", 1)
            heading = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            if body:
                chunks.append({"doc": doc_title, "source": path.name, "section": heading, "text": body})
    return chunks


_CHUNKS = _load_chunks()


def search(query: str, top_k: int = 4) -> list[dict]:
    """Returns the top_k enablement doc sections most relevant to the query."""
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored = []
    for chunk in _CHUNKS:
        body_terms = _tokenize(chunk["text"])
        heading_terms = _tokenize(chunk["section"])
        body_hits = sum(body_terms.count(t) for t in query_terms)
        heading_hits = sum(heading_terms.count(t) for t in query_terms) * 3  # headings weigh more
        score = body_hits + heading_hits
        if score > 0:
            scored.append({**chunk, "score": score})

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:top_k]


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "churn risk renewal"
    for r in search(q):
        print(f"[{r['score']}] {r['source']} :: {r['section']}")
        print(r["text"][:200].replace("\n", " ") + "...\n")
