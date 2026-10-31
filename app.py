import os
import sys

# Ensure src/ is on python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from autovideo.api.app import main

if __name__ == "__main__":
    main()
