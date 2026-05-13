#!/usr/bin/env python3
"""Sync della Roadmap Ebdomadario da Notion → data.json.

Pesca tutte le pagine del database via API Notion, le normalizza nello schema
atteso dalla dashboard, e scrive data.json nella root del repo.

Solo standard library: nessuna dipendenza esterna.

Configurazione via env:
  NOTION_TOKEN        token dell'integrazione interna Notion (obbligatorio)
  NOTION_DATABASE_ID  ID del database (default: roadmap ebdomadario)
  OUTPUT_PATH         path di output (default: ./data.json)
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"  # versione stabile e ben documentata
DEFAULT_DATABASE_ID = "10a2e982-2933-4a8d-aeb3-a3be3d90ce6e"


def get_env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        print(f"ERRORE: variabile d'ambiente {name} non impostata", file=sys.stderr)
        sys.exit(1)
    return v


def post_json(url, headers, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        print(f"ERRORE HTTP {e.code} su {url}: {msg}", file=sys.stderr)
        raise
    except urllib.error.URLError as e:
        print(f"ERRORE rete: {e}", file=sys.stderr)
        raise


def query_database(token, database_id):
    """Pagina su tutta la collection con cursor-based pagination."""
    url = f"{NOTION_API_URL}/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    results = []
    next_cursor = None
    while True:
        body = {"page_size": 100}
        if next_cursor:
            body["start_cursor"] = next_cursor
        data = post_json(url, headers, body)
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        next_cursor = data.get("next_cursor")
    return results


def get_text(prop):
    """Estrae testo concatenato da rich_text o title."""
    if not prop:
        return ""
    items = prop.get("rich_text") or prop.get("title") or []
    return "".join(it.get("plain_text", "") for it in items).strip()


def get_select(prop):
    if not prop:
        return None
    sel = prop.get("select")
    if not sel:
        return None
    return sel.get("name")


def normalize(page):
    """Mappa una page Notion nello schema atteso dalla dashboard."""
    props = page.get("properties", {})
    aggiornato = (props.get("Aggiornato il") or {}).get("last_edited_time")
    if not aggiornato:
        aggiornato = page.get("last_edited_time", "")
    return {
        "id":            page.get("id", ""),
        "codice":        get_text(props.get("Codice")),
        "nome":          get_text(props.get("Nome")),
        "categoria":     get_select(props.get("Categoria")),
        "stato":         get_select(props.get("Stato")),
        "priorita":      get_select(props.get("Priorità")),
        "decisioni":     get_text(props.get("Decisioni collegate")),
        "note":          get_text(props.get("Note")),
        "aggiornato_il": aggiornato,
    }


def main():
    token = get_env("NOTION_TOKEN", required=True)
    database_id = get_env("NOTION_DATABASE_ID", default=DEFAULT_DATABASE_ID)
    output_path = get_env("OUTPUT_PATH", default="./data.json")

    print(f"Query database {database_id}…")
    pages = query_database(token, database_id)
    print(f"  ricevute {len(pages)} pagine.")

    items = [normalize(p) for p in pages]
    # Filtra pagine completamente vuote (senza codice né nome)
    items = [it for it in items if it["codice"] or it["nome"]]

    out = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": items,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Scritto {output_path} con {len(items)} voci.")


if __name__ == "__main__":
    main()
