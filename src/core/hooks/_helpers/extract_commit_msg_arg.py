import re
import sys

cmd = sys.stdin.read()
m = re.search(r"-m\s+'((?:[^'\\]|\\.)*)'", cmd, re.DOTALL)
if not m:
    m = re.search(r'-m\s+"((?:[^"\\]|\\.)*)"', cmd, re.DOTALL)
sys.stdout.write(m.group(1) if m else "")
