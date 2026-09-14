"""Export reviewable JSON schemas from the maintenance protocol's typed records."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from likewatch_manager.models import RECORDS, json_schema

for record in RECORDS:
    destination = ROOT / 'deployment/schemas' / (record.__name__ + '.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': record.__name__, **json_schema(record)}
    destination.write_text(json.dumps(schema, indent=2) + '\n')
