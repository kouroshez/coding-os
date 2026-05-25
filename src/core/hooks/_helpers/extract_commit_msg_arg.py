import re
import sys

cmd = sys.stdin.read()

FLAG = r"(?:-m|--message)"
PATTERN = re.compile(
    rf"{FLAG}(?:\s+|=)'((?:[^'\\]|\\.)*)'"
    rf"|{FLAG}(?:\s+|=)\"((?:[^\"\\]|\\.)*)\"",
    re.DOTALL,
)

parts: list[str] = []
for m in PATTERN.finditer(cmd):
    parts.append(m.group(1) if m.group(1) is not None else m.group(2))

sys.stdout.write("\n\n".join(parts))
