import pytest
import mongomock
from pathlib import Path


@pytest.fixture
def sample_csv(tmp_path: Path):
    p = tmp_path / "sample.csv"
    p.write_text(
        "Name,Age,Gender,Blood Type,Medical Condition,Date of Admission,Doctor,Hospital,Insurance Provider,Billing Amount,Room Number,Admission Type,Discharge Date,Medication,Test Results\n"
        "Alice Dupont,30,Female,A+,Asthma,2024-01-15,Dr. Martin,Hopital Nord,Aetna,1500.50,101,Urgent,2024-01-20,Paracetamol,Normal\n"
        "Alice Dupont,30,Female,A+,Asthma,2024-01-15,Dr. Martin,Hopital Nord,Aetna,1500.50,101,Urgent,2024-01-20,Paracetamol,Normal\n"
        "Bob Martin,45,Male,O-,Diabetes,2024-02-01,Dr. Leroy,Hopital Sud,Medicare,2300.00,205,Emergency,2024-02-10,Ibuprofen,Abnormal\n",
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def mongo_client_mock(monkeypatch):
    from loader import loader
    mock_client = mongomock.MongoClient()
    monkeypatch.setattr(loader, "MongoClient", lambda *a, **k: mock_client)
    return mock_client
