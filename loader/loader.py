# loader.py - migration du CSV healthcare vers MongoDB

import os
import sys
import pandas as pd
from pymongo import MongoClient, ASCENDING
from pymongo.errors import BulkWriteError


def log(msg):
    print(f"[loader] {msg}", flush=True)


def sanitize_columns(df):
    # nettoyage des noms de colonnes (espaces, points, tirets -> underscore)
    df = df.rename(
        columns=lambda c: c.strip().replace(" ", "_").replace(".", "_").replace("-", "_")
    )
    return df


def try_parse_dates(df):
    # essaie de convertir en datetime les colonnes qui contiennent "date"
    for col in df.columns:
        if "date" in col.lower():
            try:
                df[col] = pd.to_datetime(df[col], errors="coerce")
            except Exception:
                pass
    return df


def main():
    # config via variables d'env (passées par docker-compose)
    mongo_host = os.getenv("MONGO_HOST", "mongodb")
    mongo_port = int(os.getenv("MONGO_PORT", "27017"))
    mongo_db = os.getenv("MONGO_DB", "healthcare")
    mongo_col = os.getenv("MONGO_COLLECTION", "patients")
    app_user = os.getenv("APP_USER", "appuser")
    app_pass = os.getenv("APP_PASSWORD", "appsecret")
    csv_path = os.getenv("CSV_PATH", "/data/healthcare_dataset.csv")

    if not os.path.exists(csv_path):
        log(f"CSV introuvable : {csv_path}")
        sys.exit(1)

    # connexion mongo
    uri = f"mongodb://{app_user}:{app_pass}@{mongo_host}:{mongo_port}/{mongo_db}"
    log(f"Connexion à {uri.replace(app_pass, '***')}")
    client = MongoClient(uri)
    db = client[mongo_db]
    coll = db[mongo_col]

    log(f"Lecture du CSV : {csv_path}")
    df = pd.read_csv(csv_path)
    original_rows = len(df)
    log(f"Nombre de lignes brutes : {original_rows}")

    df = sanitize_columns(df)
    log(f"Colonnes après nettoyage : {list(df.columns)}")

    df = try_parse_dates(df)

    # suppression des doublons
    # on cherche d'abord si y'a une colonne qui ressemble à un ID
    id_candidates = [
        c for c in df.columns if c.lower() in ("patientid", "patient_id", "id", "_id")
    ]
    if id_candidates:
        df = df.drop_duplicates(subset=[id_candidates[0]])
        log(f"Déduplication sur '{id_candidates[0]}' → {len(df)} lignes")
    else:
        df = df.drop_duplicates()
        log(f"Déduplication globale → {len(df)} lignes")

    # NaN -> None pour que ça passe en BSON
    df = df.where(pd.notnull(df), None)

    records = df.to_dict(orient="records")
    log(f"{len(records)} enregistrements prêts (sur {original_rows} bruts)")

    # creation des index
    if "patient_id" in df.columns:
        coll.create_index([("patient_id", ASCENDING)], name="idx_patient_id")
        log("Index idx_patient_id créé")

    if "Name" in df.columns:
        coll.create_index([("Name", ASCENDING)], name="idx_name")
        log("Index idx_name créé")

    if "Medical_Condition" in df.columns:
        coll.create_index([("Medical_Condition", ASCENDING)], name="idx_medical_condition")
        log("Index idx_medical_condition créé")

    # index composé pour les requetes sur profil patient
    if "Age" in df.columns and "Gender" in df.columns:
        coll.create_index(
            [("Age", ASCENDING), ("Gender", ASCENDING)], name="idx_age_gender"
        )
        log("Index composé idx_age_gender créé")

    # insertion
    try:
        if records:
            result = coll.insert_many(records, ordered=False)
            log(f"{len(result.inserted_ids)} documents insérés avec succès.")
        else:
            log("Aucun enregistrement à insérer.")
    except BulkWriteError as bwe:
        log(f"Erreur d'écriture groupée : {bwe.details}")
    finally:
        count = coll.count_documents({})
        log(f"Nombre total de documents dans la collection : {count}")


if __name__ == "__main__":  # pragma: no cover
    main()
