from loader import loader
import pandas as pd
import mongomock
import pytest
from unittest.mock import MagicMock
from pymongo.errors import BulkWriteError


# ── Tests unitaires des fonctions ──

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


def test_try_parse_dates_exception_silenced(monkeypatch):
    """Si pd.to_datetime lève une exception inattendue, pas de crash."""
    df = pd.DataFrame({"date_col": [1, 2, 3]})
    monkeypatch.setattr(pd, "to_datetime", lambda *a, **k: (_ for _ in ()).throw(TypeError("boom")))
    result = loader.try_parse_dates(df)
    assert list(result["date_col"]) == [1, 2, 3]


# ── Tests de validation / intégrité des données ──

EXPECTED_COLUMNS = [
    "Name", "Age", "Gender", "Blood_Type", "Medical_Condition",
    "Date_of_Admission", "Doctor", "Hospital", "Insurance_Provider",
    "Billing_Amount", "Room_Number", "Admission_Type", "Discharge_Date",
    "Medication", "Test_Results",
]


def _build_sample_df():
    """Construit un DataFrame réaliste avec doublons et colonnes brutes."""
    return pd.DataFrame({
        "Name": ["Alice Dupont", "Alice Dupont", "Bob Martin", "Claire Noir"],
        "Age": [30, 30, 45, None],
        "Gender": ["Female", "Female", "Male", "Female"],
        "Blood Type": ["A+", "A+", "O-", "B+"],
        "Medical Condition": ["Asthma", "Asthma", "Diabetes", "Cancer"],
        "Date of Admission": ["2024-01-15", "2024-01-15", "2024-02-01", "bad date"],
        "Doctor": ["Dr. Martin", "Dr. Martin", "Dr. Leroy", "Dr. Blanc"],
        "Hospital": ["Hôpital Nord", "Hôpital Nord", "Hôpital Sud", "Hôpital Est"],
        "Insurance Provider": ["Aetna", "Aetna", "Medicare", "Cigna"],
        "Billing Amount": [1500.50, 1500.50, 2300.00, 890.00],
        "Room Number": [101, 101, 205, 310],
        "Admission Type": ["Urgent", "Urgent", "Emergency", "Elective"],
        "Discharge Date": ["2024-01-20", "2024-01-20", "2024-02-10", "2024-03-05"],
        "Medication": ["Paracetamol", "Paracetamol", "Ibuprofen", "Aspirin"],
        "Test Results": ["Normal", "Normal", "Abnormal", "Inconclusive"],
    })


def test_schema_columns_after_sanitize():
    """Vérifie que les 15 colonnes attendues sont présentes après nettoyage."""
    df = _build_sample_df()
    df = loader.sanitize_columns(df)
    assert sorted(df.columns.tolist()) == sorted(EXPECTED_COLUMNS)


def test_no_spaces_dots_dashes_in_column_names():
    """Aucun nom de colonne ne doit contenir d'espace, point ou tiret."""
    df = _build_sample_df()
    df = loader.sanitize_columns(df)
    for col in df.columns:
        assert " " not in col, f"Espace trouvé dans '{col}'"
        assert "." not in col, f"Point trouvé dans '{col}'"
        assert "-" not in col, f"Tiret trouvé dans '{col}'"


def test_date_columns_are_datetime():
    """Les colonnes contenant 'date' doivent être de type datetime64."""
    df = _build_sample_df()
    df = loader.sanitize_columns(df)
    df = loader.try_parse_dates(df)
    for col in df.columns:
        if "date" in col.lower():
            assert pd.api.types.is_datetime64_any_dtype(df[col]), \
                f"'{col}' devrait être datetime, pas {df[col].dtype}"


def test_invalid_dates_become_nat():
    """Les dates invalides doivent être NaT, pas lever d'erreur."""
    df = _build_sample_df()
    df = loader.sanitize_columns(df)
    df = loader.try_parse_dates(df)
    # la ligne #3 a "bad date" dans Date_of_Admission
    assert pd.isna(df["Date_of_Admission"].iloc[3])


def test_dedup_removes_exact_duplicates():
    """La déduplication doit supprimer les lignes identiques."""
    df = _build_sample_df()
    df = loader.sanitize_columns(df)
    before = len(df)
    df = df.drop_duplicates()
    after = len(df)
    assert after < before, "Des doublons auraient dû être supprimés"
    assert after == 3, f"Attendu 3 lignes uniques, obtenu {after}"


def test_nan_replaced_by_none():
    """Les NaN doivent devenir None (ou NaN) pour la compatibilité BSON."""
    df = _build_sample_df()
    df = loader.sanitize_columns(df)
    df = df.drop_duplicates()
    df = df.where(pd.notnull(df), None)
    records = df.to_dict(orient="records")
    # la ligne Claire Noir a Age manquant
    claire = [r for r in records if r["Name"] == "Claire Noir"][0]
    assert claire["Age"] is None or pd.isna(claire["Age"]), \
        f"Age devrait être None ou NaN, pas {claire['Age']}"


def test_row_count_coherent_after_pipeline():
    """Le nombre de lignes après pipeline doit être <= au nombre brut."""
    df = _build_sample_df()
    raw_count = len(df)
    df = loader.sanitize_columns(df)
    df = loader.try_parse_dates(df)
    df = df.drop_duplicates()
    assert len(df) <= raw_count
    assert len(df) > 0


# ── Tests du pipeline complet (insertion MongoDB) ──

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


def test_main_dedup_on_patient_id(monkeypatch, capsys):
    """Quand une colonne patient_id existe, la dédup se fait dessus."""
    fake_df = pd.DataFrame({
        "patient_id": [1, 1, 2],
        "Name": ["Alice", "Alice bis", "Bob"],
        "Age": [30, 31, 40],
        "Gender": ["F", "F", "M"],
        "Medical_Condition": ["Asthma", "Diabetes", "Cancer"],
    })
    monkeypatch.setattr(pd, "read_csv", lambda path: fake_df)
    monkeypatch.setenv("CSV_PATH", "/fake.csv")
    monkeypatch.setattr(loader.os.path, "exists", lambda p: True)
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(loader, "MongoClient", lambda *a, **k: mock_client)

    loader.main()

    coll = mock_client["healthcare"]["patients"]
    assert coll.count_documents({}) == 2
    out = capsys.readouterr().out
    assert "patient_id" in out


def test_main_empty_dataframe(monkeypatch, capsys):
    """Un DataFrame vide ne doit pas planter."""
    fake_df = pd.DataFrame(columns=["Name", "Age", "Gender", "Medical_Condition"])
    monkeypatch.setattr(pd, "read_csv", lambda path: fake_df)
    monkeypatch.setenv("CSV_PATH", "/fake.csv")
    monkeypatch.setattr(loader.os.path, "exists", lambda p: True)
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(loader, "MongoClient", lambda *a, **k: mock_client)

    loader.main()

    out = capsys.readouterr().out
    assert "Aucun enregistrement" in out


def test_main_bulk_write_error(monkeypatch, capsys):
    """En cas de BulkWriteError, le script log l'erreur sans crasher."""
    fake_df = pd.DataFrame({
        "Name": ["Alice"], "Age": [30], "Gender": ["F"],
        "Medical_Condition": ["Asthma"],
    })
    monkeypatch.setattr(pd, "read_csv", lambda path: fake_df)
    monkeypatch.setenv("CSV_PATH", "/fake.csv")
    monkeypatch.setattr(loader.os.path, "exists", lambda p: True)

    mock_coll = MagicMock()
    mock_coll.insert_many.side_effect = BulkWriteError(
        {"writeErrors": [{"errmsg": "dup key"}], "writeConcernErrors": [], "nInserted": 0}
    )
    mock_coll.count_documents.return_value = 0
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_coll)
    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    monkeypatch.setattr(loader, "MongoClient", lambda *a, **k: mock_client)

    loader.main()

    out = capsys.readouterr().out
    assert "Erreur d\u2019\u00e9criture group\u00e9e" in out or "Erreur" in out
