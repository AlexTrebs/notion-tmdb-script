from config import Settings
from typing import Callable

settings = Settings()

DefHandler = Callable[[dict], dict]

def get_directors(crew: list[dict]) -> list[str]:
  """Extract all crew members with job == 'Director'."""
  return [m["name"] for m in crew if m.get("job") == "Director"]

PROP_HANDLERS: dict[str, DefHandler] = {
  "Poster": lambda info: (
    {"url": settings.img_base + info["poster_path"]} if info.get("poster_path") else None
  ),
  "Genre": lambda info: {
    "multi_select": [{"name": g["name"]} for g in info.get("genres", [])]
  },
  "Director": lambda info: {
    "rich_text": [
      {
        "type": "text",
        "text": {"content": ", ".join(get_directors(info.get("credits", {}).get("crew", [])))},
      }
    ]
  },
  "Release Date": lambda info: (
    {"date": {"start": info["release_date"]}} if info.get("release_date") else None
  ),
  "Studio / Distributor": lambda info: {
    "multi_select": [{"name": c["name"]} for c in info.get("production_companies", [])]
  },
}
