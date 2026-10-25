"""Build only browser assets. No configuration, database, or source files are published."""
from pathlib import Path
import shutil
import re
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'edge_replay' / 'web'
OUTPUT = ROOT / 'public'
if OUTPUT.exists():
    shutil.rmtree(OUTPUT)
shutil.copytree(SOURCE, OUTPUT)
for page in [OUTPUT / 'workspace.html']:
    html = page.read_text().replace('</head>', '<link rel="stylesheet" href="/hosted.css">\n</head>')
    # Static build injection leaves the loopback application's templates unchanged.
    html = re.sub(r'(<script[^>]*src="/app.js")', r'<script src="/hosted.js" defer></script>\n\1', html, count=1)
    page.write_text(html)
assert (OUTPUT / 'hosted.js').exists()
print('Hosted browser assets ready in public/')
