"""python -m cave_dig

Der Videotreiber muss stehen, bevor pygame das Fenster anlegt. Darum
setzen wir --headless hier, noch vor dem Import von app.py.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if "--headless" in sys.argv:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    from cave_dig.app import main as run

    return run()


if __name__ == "__main__":
    sys.exit(main())
