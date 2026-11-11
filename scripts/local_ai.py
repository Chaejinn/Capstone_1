"""Compatibility entrypoint. AI implementation lives under Ai파일/tools/."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Ai파일.tools.local_ai import main, prerequisites, build_app

if __name__=='__main__':main()
