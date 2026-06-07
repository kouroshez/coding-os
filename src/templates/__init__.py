"""Marker so the per-stack template trees ship as wheel package-data.

The subdirectories (django/, fastapi/, nextjs/, ...) are data-only scaffolds,
NOT importable packages — they ride along via [tool.setuptools.package-data]
``templates = ["**/*"]`` so a pip/uvx-installed `cos init` finds them. TASK-219.
"""
