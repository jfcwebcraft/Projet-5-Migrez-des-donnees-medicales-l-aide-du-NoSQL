from loader import loader
import pandas as pd
import mongomock
import pytest


def test_log_prints(capsys):
    loader.log("hello")
    out = capsys.readouterr().out
    assert "[loader] hello" in out


def test_sanitize_columns_replaces_spaces_dots_dashes():
    df = pd.DataFrame({"A B": [1], "C.D": [2], "E-F": [3], " clean ": [4]})
    df2 = loader.sanitize_columns(df)
    assert set(df2.columns) == {"A_B", "C_D", "E_F", "clean"}


def test_try_parse_dates_parses_and_sets_nat():
    df = pd.DataFrame({"Visit Date": ["2024-01-01", "not a date"]})
    df = loader.sanitize_columns(df)
    out = loader.try_parse_dates(df)
    assert str(out["Visit_Date"].iloc[0]).startswith("2024-01-01")
    assert pd.isna(out["Visit_Date"].iloc[1])


def test_main_happy_path(monkeypatch):
    fake_df = pd.DataFrame(
        {
            "Name": ["Alice", "Alice", "Bob"],
            "Age": [30, 30, 40],
            "Gender": ["F", "F", "M"],
            "Medical_Condition": ["Asthma", "Asthma", "Diabetes"],
        }
    )

    monkeypatch.setattr(pd, "read_csv", lambda path: fake_df)
    monkeypatch.setenv("CSV_PATH", "/fake.csv")
    monkeypatch.setenv("MONGO_HOST", "mongodb")
    monkeypatch.setenv("MONGO_PORT", "27017")
    monkeypatch.setenv("MONGO_DB", "healthcare")
    monkeypatch.setenv("MONGO_COLLECTION", "patients")
    monkeypatch.setenv("APP_USER", "appuser")
    monkeypatch.setenv("APP_PASSWORD", "appsecret")
    monkeypatch.setattr(loader.os.path, "exists", lambda p: True)

    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(loader, "MongoClient", lambda *a, **k: mock_client)

    loader.main()

    coll = mock_client["healthcare"]["patients"]
    assert coll.count_documents({}) == 2  # 2 identiques supprimées


def test_main_exits_when_csv_missing(monkeypatch):
    monkeypatch.setattr(loader.os.path, "exists", lambda p: False)
    monkeypatch.setenv("CSV_PATH", "/missing.csv")

    with pytest.raises(SystemExit) as exc_info:
        loader.main()
    assert exc_info.value.code == 1
