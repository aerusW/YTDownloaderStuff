"""
Make the project importable no matter where pytest is invoked from.

The tests import ``src`` and ``YTDownload`` as top-level modules, which only
resolve when the project root is on ``sys.path``. Running ``python -m pytest``
from the root puts it there implicitly, but a bare ``pytest`` launched from
inside ``tests/`` does not — so add the root explicitly here.
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
