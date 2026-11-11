"""Compatibility entrypoint for the relocated AI build preparation tool."""
from pathlib import Path
import runpy

if __name__=='__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'Ai파일/tools/prepare-tracking.py'),run_name='__main__')
