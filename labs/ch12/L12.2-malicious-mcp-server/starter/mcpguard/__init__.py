"""Lab 12.2: a malicious MCP server, and the host-side checks that catch it.

Everything runs in process. The "servers" are local fixtures that answer the two MCP requests a host relies
on, `initialize` and `tools/list`, and `tools/call` for the one legitimate server, which is Lab 3.2's
constrained query tool vendored unchanged in ../vendor/. No subprocess is started and nothing leaves the machine.
"""

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
VENDOR = LAB / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))
