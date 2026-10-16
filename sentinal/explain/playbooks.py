from pathlib import Path
from typing import Any
import yaml

def load_playbooks(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path or Path(__file__).parents[1] / 'config' / 'playbooks.yaml')
    try:
        data = yaml.safe_load(path.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError): return {}

def lookup_playbook(key: str, playbooks: dict[str, Any] | None = None) -> dict[str, Any]:
    data = playbooks or load_playbooks()
    item = data.get(key, data.get('default', {}))
    return item if isinstance(item, dict) else {}
