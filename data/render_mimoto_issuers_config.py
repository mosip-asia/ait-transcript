"""Render vc-stack/config/mimoto-issuers-config.json from its .template.

The only thing that changes with deployment is where the wallet (Inji Web)
is publicly reachable — redirect_uri / token_endpoint both point back at it
(see AGENTS.md's App-level config note). INJI_WEB_URL defaults to localhost
for local dev; a public deployment sets it in vc-stack/.env.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TEMPLATE = REPO_ROOT / "vc-stack" / "config" / "mimoto-issuers-config.json.template"
OUT = REPO_ROOT / "vc-stack" / "config" / "mimoto-issuers-config.json"


def main() -> None:
    inji_web_url = os.environ.get("INJI_WEB_URL", "http://localhost:4004")
    rendered = TEMPLATE.read_text(encoding="utf-8").replace("${INJI_WEB_URL}", inji_web_url)
    OUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUT} (INJI_WEB_URL={inji_web_url})")


if __name__ == "__main__":
    main()
