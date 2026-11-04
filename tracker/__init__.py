"""YouTube Channel Tracker — summarizes new videos and logs stock moves."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
PROMPTS_DIR = ROOT / "prompts"
TEMPLATES_DIR = ROOT / "templates"
CONFIG_PATH = ROOT / "channels.yaml"

# Bump this when you change the prompts or schema. Videos analysed with an older
# version can be re-run with:  python -m tracker reprocess --stale
ANALYSIS_VERSION = 1
