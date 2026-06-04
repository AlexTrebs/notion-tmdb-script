import logging
import pytest
import notion_tmdb_updater
from handlers import PROP_HANDLERS, get_directors
from notion_tmdb_updater import _is_empty, build_filter, tmdb_to_notion_props, process_page


@pytest.fixture
def fake_page():
    return {
        "id": "page-123",
        "properties": {
            "Name":                  {"title": [{"text": {"content": "Inception"}}]},
            "Type":                  {"select": {"name": "Movie"}},
            "Genre":                 {"multi_select": []},
            "Director":              {"rich_text": []},
            "Poster":                {"url": None},
            "Studio / Distributor":  {"multi_select": []},
            "Release Date":          {"date": None},
        },
    }


# ── config ────────────────────────────────────────────────────────────────────

def test_parse_empty_map_from_json_string(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test")
    monkeypatch.setenv("NOTION_DB", "test")
    monkeypatch.setenv("TMDB_TOKEN", "test")
    monkeypatch.setenv("NOTION_EMPTY_PROPERTY_MAP", '{"Genre":"multi_select"}')
    from config import Settings
    s = Settings(_env_file=None)
    assert s.empty_map == {"Genre": "multi_select"}


def test_parse_empty_map_invalid_json_raises(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test")
    monkeypatch.setenv("NOTION_DB", "test")
    monkeypatch.setenv("TMDB_TOKEN", "test")
    monkeypatch.setenv("NOTION_EMPTY_PROPERTY_MAP", "not-valid-json")
    from config import Settings
    with pytest.raises(Exception):
        Settings(_env_file=None)


# ── handlers ──────────────────────────────────────────────────────────────────

def test_get_directors_filters_by_job():
    crew = [{"name": "Nolan", "job": "Director"}, {"name": "Smith", "job": "Producer"}]
    assert get_directors(crew) == ["Nolan"]


def test_get_directors_empty():
    assert get_directors([]) == []


def test_poster_with_path():
    result = PROP_HANDLERS["Poster"]({"poster_path": "/foo.jpg"})
    assert result == {"url": "https://image.tmdb.org/t/p/w500/foo.jpg"}


def test_poster_missing_path_returns_none():
    assert PROP_HANDLERS["Poster"]({}) is None


def test_director_no_credits_key():
    result = PROP_HANDLERS["Director"]({})
    assert result["rich_text"][0]["text"]["content"] == ""


def test_release_date_present():
    result = PROP_HANDLERS["Release Date"]({"release_date": "2024-01-01"})
    assert result == {"date": {"start": "2024-01-01"}}


def test_release_date_absent():
    result = PROP_HANDLERS["Release Date"]({})
    assert result is None


# ── _is_empty ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prop,ptype,expected", [
    ({"rich_text": []},         "rich_text",    True),
    ({"rich_text": [{"x": 1}]}, "rich_text",    False),
    ({"multi_select": []},      "multi_select", True),
    ({"url": None},             "url",          True),
    ({"url": "http://x"},       "url",          False),
    ({"date": None},            "date",         True),
    ({},                        "rich_text",    True),
])
def test_is_empty(prop, ptype, expected):
    assert _is_empty(prop, ptype) == expected


# ── build_filter ──────────────────────────────────────────────────────────────

def test_build_filter_structure():
    f = build_filter()
    assert "and" in f
    top = f["and"]
    assert top[0]["property"] == notion_tmdb_updater.settings.title_prop
    assert top[0]["title"] == {"is_not_empty": True}
    assert "or" in top[1]
    prop_names = [c["property"] for c in top[1]["or"]]
    assert "Genre" in prop_names


# ── tmdb_to_notion_props ──────────────────────────────────────────────────────

def test_skips_already_filled_field():
    page_props = {
        "Genre":                {"multi_select": [{"name": "Action"}]},
        "Director":             {"rich_text": []},
        "Poster":               {"url": None},
        "Studio / Distributor": {"multi_select": []},
        "Release Date":         {"date": None},
    }
    info = {
        "genres": [{"name": "Drama"}],
        "credits": {"crew": [{"name": "X", "job": "Director"}]},
        "poster_path": "/x.jpg",
        "production_companies": [],
        "release_date": "2024-01-01",
    }
    props = tmdb_to_notion_props(info, page_props)
    assert "Genre" not in props
    assert "Director" in props


def test_skips_handler_returning_none():
    page_props = {
        "Poster":               {"url": None},
        "Genre":                {"multi_select": []},
        "Director":             {"rich_text": []},
        "Studio / Distributor": {"multi_select": []},
        "Release Date":         {"date": None},
    }
    info = {"genres": [], "credits": {"crew": []}, "production_companies": []}
    props = tmdb_to_notion_props(info, page_props)
    assert "Poster" not in props


# ── process_page (e2e) ────────────────────────────────────────────────────────

def test_process_page_full(mocker, fake_page):
    mocker.patch("notion_tmdb_updater.tmdb_search", return_value=27205)
    mocker.patch("notion_tmdb_updater.tmdb_details", return_value={
        "genres": [{"name": "Sci-Fi"}],
        "credits": {"crew": [{"name": "Nolan", "job": "Director"}]},
        "poster_path": "/inception.jpg",
        "production_companies": [{"name": "WB"}],
        "release_date": "2010-07-16",
    })
    update = mocker.patch.object(notion_tmdb_updater.notion.pages, "update")

    process_page(fake_page)

    update.assert_called_once()
    props = update.call_args.kwargs["properties"]
    assert props["Genre"] == {"multi_select": [{"name": "Sci-Fi"}]}
    assert "Nolan" in props["Director"]["rich_text"][0]["text"]["content"]
    assert "inception.jpg" in props["Poster"]["url"]


def test_process_page_skips_filled_fields(mocker, fake_page):
    fake_page["properties"]["Genre"]["multi_select"] = [{"name": "Action"}]
    mocker.patch("notion_tmdb_updater.tmdb_search", return_value=27205)
    mocker.patch("notion_tmdb_updater.tmdb_details", return_value={
        "genres": [{"name": "Drama"}],
        "credits": {"crew": []},
        "poster_path": None,
        "production_companies": [],
        "release_date": None,
    })
    update = mocker.patch.object(notion_tmdb_updater.notion.pages, "update")

    process_page(fake_page)

    update.assert_called_once()
    props = update.call_args.kwargs["properties"]
    assert "Genre" not in props


def test_process_page_logs_error_on_failure(mocker, fake_page, caplog):
    mocker.patch("notion_tmdb_updater.tmdb_search", side_effect=ValueError("no results"))
    mocker.patch.object(notion_tmdb_updater.notion.pages, "update")

    with caplog.at_level(logging.ERROR):
        process_page(fake_page)

    assert "Inception" in caplog.text
    assert "no results" in caplog.text


def test_process_page_tv_kind(mocker, fake_page):
    fake_page["properties"]["Type"]["select"]["name"] = "Series"
    search = mocker.patch("notion_tmdb_updater.tmdb_search", return_value=1396)
    mocker.patch("notion_tmdb_updater.tmdb_details", return_value={
        "genres": [{"name": "Drama"}],
        "credits": {"crew": []},
        "poster_path": None,
        "production_companies": [],
        "release_date": "2008-01-20",
    })
    mocker.patch.object(notion_tmdb_updater.notion.pages, "update")

    process_page(fake_page)

    assert search.call_args.args[0] == "tv"


def test_process_page_empty_title_logs_error(mocker, fake_page, caplog):
    fake_page["properties"]["Name"]["title"] = []
    mocker.patch("notion_tmdb_updater.tmdb_search", side_effect=ValueError("no results"))
    mocker.patch.object(notion_tmdb_updater.notion.pages, "update")

    with caplog.at_level(logging.ERROR):
        process_page(fake_page)

    assert "no results" in caplog.text


def test_is_empty_empty_string_url():
    assert _is_empty({"url": ""}, "url") is True


def test_is_empty_zero_number_not_empty():
    assert _is_empty({"number": 0}, "number") is False
