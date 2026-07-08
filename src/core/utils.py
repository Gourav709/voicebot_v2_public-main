import json
from pathlib import Path

def read_text(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')

def extract_json_object(s: str) -> str:
    s=(s or '').strip()
    i=s.find('{'); j=s.rfind('}')
    if i!=-1 and j!=-1 and j>i:
        return s[i:j+1]
    return s

def safe_json_loads(s: str):
    return json.loads(extract_json_object(s))
