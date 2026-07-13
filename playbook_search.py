"""
Search tool over the sales enablement docs (playbook, ICP, battlecards,
objection handling, pricing, case studies).

Retrieval approach: split each doc into its "## " sections (further split into
"### " subsections where a section packs several distinct items, e.g.
objection_handling.md's ten objections under one "Common objections"
heading - without that second split, a query about one specific objection
loses to a merely topically-adjacent doc, since the whole ten-objection block
scores as a single chunk), score chunks by keyword overlap with the query,
return the top matches. With only 7 short docs (~800 lines total), a full
embeddings/vector-store pipeline isn't justified — keyword scoring over
section-sized chunks is simple, fast, and easy to reason about. Would move to
embeddings if the corpus grew materially.
"""

import math
import re
from collections import Counter
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


def _split_subsections(heading: str, body: str) -> list[tuple[str, str]]:
    """Some sections (e.g. objection_handling.md's "Common objections") pack
    many distinct "### " subsections under one "## " heading - without this,
    a query about one specific objection loses to a doc that's merely
    topically-adjacent, because the whole ten-objection block scores as a
    single undifferentiated chunk. Split those out; leave sections with no
    "### " subheadings alone."""
    if "\n### " not in "\n" + body:
        return [(heading, body)]

    parts = re.split(r"^###\s+", body, flags=re.MULTILINE)
    result = []
    if parts[0].strip():
        result.append((heading, parts[0].strip()))
    for part in parts[1:]:
        lines = part.split("\n", 1)
        sub_heading = lines[0].strip()
        sub_body = lines[1].strip() if len(lines) > 1 else ""
        if sub_body:
            result.append((f"{heading} → {sub_heading}", sub_body))
    return result


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
            if not body:
                continue
            for sub_heading, sub_body in _split_subsections(heading, body):
                chunks.append({"doc": doc_title, "source": path.name, "section": sub_heading, "text": sub_body})
    return chunks


_CHUNKS = _load_chunks()


def _compute_idf(chunks: list[dict]) -> dict[str, float]:
    """Down-weights terms that show up in many chunks, up-weights rare ones.
    Found via testing that this matters, not just in theory: a query like
    "deal stuck in qualification" was losing the playbook's own Qualification
    section to its Discovery section, because "discovery" appears constantly
    across the doc (diluting how specific a signal it actually is) while
    "qualification" is rare but landed in a section too short to rack up raw
    term-frequency hits. Still plain keyword retrieval, not embeddings - this
    is the natural next step from counting term frequency, appropriate
    regardless of corpus size, not a step toward a vector store."""
    doc_freq = Counter()
    for chunk in chunks:
        terms = set(_tokenize(chunk["text"])) | set(_tokenize(chunk["section"]))
        doc_freq.update(terms)
    n = len(chunks)
    return {term: math.log(n / (1 + df)) + 1 for term, df in doc_freq.items()}


_IDF = _compute_idf(_CHUNKS)


def search(query: str, top_k: int = 5) -> list[dict]:
    """Returns the top_k enablement doc sections most relevant to the query."""
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored = []
    for chunk in _CHUNKS:
        body_terms = _tokenize(chunk["text"])
        heading_terms = _tokenize(chunk["section"])
        score = 0.0
        for t in query_terms:
            weight = _IDF.get(t, 1.0)
            score += body_terms.count(t) * weight
            score += heading_terms.count(t) * weight * 3  # headings weigh more
        if score > 0:
            scored.append({**chunk, "score": round(score, 2)})

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:top_k]


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "churn risk renewal"
    for r in search(q):
        print(f"[{r['score']}] {r['source']} :: {r['section']}")
        print(r["text"][:200].replace("\n", " ") + "...\n")
