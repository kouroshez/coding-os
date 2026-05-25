import re
import sys

cmd = sys.stdin.read()

parts: list[str] = []
for m in re.finditer(r"-m\s+'((?:[^'\\]|\\.)*)'|-m\s+\"((?:[^\"\\]|\\.)*)\"", cmd, re.DOTALL):
    parts.append(m.group(1) if m.group(1) is not None else m.group(2))

sys.stdout.write("\n\n".join(parts))
