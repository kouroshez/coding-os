"""graph_os storage backends.

Two implementations ship in I.0:
  - SqliteBackend — fallback, always available, reuses thinking_os DB.
  - KuzuBackend   — primary, optional extra (pip install kuzu).

Both honour the GraphBackend Protocol (../backend.py) and the Section
12.6 parity contract — they return identical results for the I.0
parity matrix.
"""
