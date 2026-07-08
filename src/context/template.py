from typing import Dict, Any

def render_template(text: str, variables: Dict[str, Any]) -> str:
    out=text
    for k,v in variables.items():
        out=out.replace('{' + k + '}', str(v))
    return out
