import sys, os

# Must run before any project module is imported (module-level Settings() calls)
os.environ["NOTION_TOKEN"] = "test-notion-token"
os.environ["NOTION_DB"]    = "test-db-id"
os.environ["TMDB_TOKEN"]   = "test-tmdb-token"
os.environ["NOTION_EMPTY_PROPERTY_MAP"] = (
    '{"Director":"rich_text","Poster":"url","Genre":"multi_select",'
    '"Studio / Distributor":"multi_select","Release Date":"date"}'
)

sys.path.insert(0, os.path.dirname(__file__))
