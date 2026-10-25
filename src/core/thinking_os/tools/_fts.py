"""FTS5 query text for the lexical fallback of the docs and task searches."""

from __future__ import annotations


def _fts5_any_term_query(query: str) -> str:
    # Each word quoted as a phrase so FTS5 metacharacters (:, ", *, parens and
    # bareword AND/OR/NEAR) stay literal, then OR-joined: a natural-language
    # query matches rows holding any of its words and bm25 ranks those holding
    # more of them first. The space-joined form ANDs every word, so an 8-word
    # question matched nothing.
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in query.split() if t)
