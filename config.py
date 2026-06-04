import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator
from typing import Dict

class Settings(BaseSettings):
  # Notion
  notion_token: str              = Field(..., alias="NOTION_TOKEN")
  database_id: str               = Field(..., alias="NOTION_DB")
  title_prop: str                = Field("Name", alias="NOTION_DB_TITLE")
  empty_map: Dict[str, str]      = Field(..., alias="NOTION_EMPTY_PROPERTY_MAP")

  # TMDB
  tmdb_token: str                = Field(..., alias="TMDB_TOKEN")
  tmdb_base: str                 = "https://api.themoviedb.org/3"
  img_base: str                  = "https://image.tmdb.org/t/p/w500"

  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8"
  )

  @validator("empty_map", pre=True)
  def _parse_empty_map(cls, v):
    # allow passing a JSON string in the env var
    if isinstance(v, str):
      return json.loads(v)
    return v