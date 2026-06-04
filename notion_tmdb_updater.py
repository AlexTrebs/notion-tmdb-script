import logging
import requests

from config import Settings
from concurrent.futures import ThreadPoolExecutor
from handlers import PROP_HANDLERS
from functools import lru_cache
from notion_client import Client

# Setup logging and config
logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s %(levelname)s %(message)s",
)

settings = Settings()
notion   = Client(auth=settings.notion_token)
HEADERS  = {
  "accept":        "application/json",
  "Authorization": f"Bearer {settings.tmdb_token}"
}


def build_filter() -> dict:
  """Build a filter: title exists AND any target field is empty."""
  empty_clauses = [
    {"property": prop_name, empty_type: {"is_empty": True}}
    for prop_name, empty_type in settings.empty_map.items()
  ]
  return {
    "and": [
      {"property": settings.title_prop, "title": {"is_not_empty": True}},
      {"or": empty_clauses},
    ]
  }


def fetch_pages_missing_field() -> list[dict]:
  """Page through Notion and return all rows matching our empty-field filter."""
  all_pages = []
  cursor    = None
  filter_body = build_filter()

  while True:
    response = notion.databases.query(
      database_id=settings.database_id,
      filter=filter_body,
      start_cursor=cursor,
      page_size=100
    )

    # Keep adding pages until there are no more
    all_pages.extend(response["results"])
    if not response.get("has_more"):
      break
    cursor = response.get("next_cursor")

  return all_pages


@lru_cache(maxsize=256)
def tmdb_search(kind: str, query: str) -> int:
  """Return the first TMDB ID matching our query."""
  url = f"{settings.tmdb_base}/search/{kind}"
  response = requests.get(url, headers=HEADERS, params={"query": query})

  response.raise_for_status()

  results = response.json().get("results", [])
  if not results:
    raise ValueError(f"No TMDB results for {kind} '{query}'")
  return results[0]["id"]


@lru_cache(maxsize=256)
def tmdb_details(kind: str, tmdb_id: int) -> dict:
  """Fetch full details + credits for a given TMDB ID."""
  url = f"{settings.tmdb_base}/{kind}/{tmdb_id}"
  response = requests.get(
    url,
    headers=HEADERS,
    params={"append_to_response": "credits"}
  )

  response.raise_for_status()

  return response.json()


def _is_empty(notion_prop: dict, prop_type: str) -> bool:
  val = notion_prop.get(prop_type)
  if val is None:
    return True
  if isinstance(val, list):
    return len(val) == 0
  if isinstance(val, str):
    return val == ""
  return False


def tmdb_to_notion_props(info: dict, page_props: dict) -> dict:
  """Build a Notion properties payload for fields that are currently empty on the page."""
  props: dict[str, dict] = {}

  for prop_name, prop_type in settings.empty_map.items():
    if not _is_empty(page_props.get(prop_name, {}), prop_type):
      continue
    if handler := PROP_HANDLERS.get(prop_name):
      result = handler(info)
      if result is not None:
        props[prop_name] = result
      continue

    # generic fallback
    key = prop_name.lower().replace(" / ", "_").replace(" ", "_")
    raw = info.get(key)

    if raw is not None:
      if prop_type == "number" and isinstance(raw, (int, float)):
        props[prop_name] = {"number": raw}
      else:
        props[prop_name] = {
          "rich_text": [
            {"type": "text", "text": {"content": str(raw)}}
          ]
        }
    # else: no value from TMDB — skip rather than send null

  return props


def process_page(page: dict):
  """Fetch TMDB info for one Notion row and update it."""
  title = ""
  try:
    title_block = page["properties"][settings.title_prop]["title"]
    title = title_block[0]["text"]["content"] if title_block else ""

    # derive kind from Notion select or fallback
    select = page["properties"].get("Type", {}).get("select")
    raw_kind = (select or {}).get("name", "").lower()
    kind = "movie" if raw_kind in ("movie", "film") else "tv"
    if not raw_kind:
      logging.warning("No Type set for '%s', defaulting to tv", title)

    tmdb_id = tmdb_search(kind, title)
    info = tmdb_details(kind, tmdb_id)
    props  = tmdb_to_notion_props(info, page["properties"])

    notion.pages.update(page_id=page["id"], properties=props)
    logging.info("Updated '%s'", title)

  except Exception as e:
    logging.error("Failed '%s': %s", title, e, exc_info=True)


if __name__ == "__main__":
  pages = fetch_pages_missing_field()
  logging.info("Found %d pages to update", len(pages))

  # Parallelize the I/O-bound work
  with ThreadPoolExecutor(max_workers=10) as pool:
    pool.map(process_page, pages)
