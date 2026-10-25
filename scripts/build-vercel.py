"""Copy only frontend assets into Vercel's CDN directory."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
public = root / "public"
public.mkdir(exist_ok=True)
for page in (root / "code").glob("*.html"):
    shutil.copy2(page, public / page.name)
for name in ("signal-sw.js", "signal-test.webmanifest"):
    shutil.copy2(root / "code" / name, public / name)
for directory in ("css", "js"):
    shutil.copytree(root / "code" / directory, public / directory, dirs_exist_ok=True)
print("Frontend assets prepared in public/")
