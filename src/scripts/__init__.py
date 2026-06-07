"""Marker so the bundled shell scripts (git-hook bodies, installers) ship as
wheel package-data. The .sh files ride along via package-data so an installed
`cos init` can install consumer git hooks. TASK-219.
"""
