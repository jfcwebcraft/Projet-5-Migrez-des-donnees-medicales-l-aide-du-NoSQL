# Migration de données médicales vers MongoDB (Docker)

Projet de migration d'un dataset CSV de données médicales patients vers MongoDB, le tout conteneurisé avec Docker Compose.

## Structure du projet

```
├── data/
│   └── healthcare_dataset.csv       # dataset (non versionné)
├── initdb/
│   └── init-mongo.js                # creation des users mongo au demarrage
├── loader/
│   ├── Dockerfile
│   └── loader.py                    # script de migration
├── test_unitaire/
│   ├── conftest.py
│   └── test_loader.py
├── .env.example
├── docker-compose.yml
├── cheat_sheet_mongo.md
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

## Comment lancer

Il faut Docker et Docker Compose.

```bash
# copier le .env et adapter les mots de passe
cp .env.example .env

# placer le CSV dans data/
# (le fichier healthcare_dataset.csv fourni par le client)

# lancer
docker compose up -d --build

# voir les logs de la migration
docker compose logs loader
```

## Ce qui se passe pendant la migration

Le script `loader.py` fait les étapes suivantes :

1. Vérifie que le CSV existe (sinon exit)
2. Se connecte à MongoDB avec l'user applicatif
3. Lit le CSV avec pandas
4. Nettoie les noms de colonnes (espaces, tirets, points → underscores)
5. Essaie de convertir les colonnes contenant "date" en datetime
6. Supprime les doublons (sur un ID si y'en a un, sinon en global)
7. Remplace les NaN par None (pour que ça passe en BSON)
8. Crée les index (sur Name, Medical_Condition, et un composé Age+Gender)
9. Insère tout d'un coup avec insert_many

Sur notre dataset de 55 500 lignes, ça donne 54 966 documents (534 doublons virés).

## Vérifier que ça a marché

```bash
docker exec -it mongodb mongosh -u admin -p adminpass --authenticationDatabase admin
```

```js
use healthcare
db.patients.countDocuments({})   // 54966
db.patients.findOne()
db.patients.getIndexes()
```

## Schéma de la collection patients

Chaque document correspond à un patient :

| Champ | Type | Description |
|-------|------|-------------|
| Name | string | Nom du patient |
| Age | int | Age |
| Gender | string | Male/Female |
| Blood_Type | string | Groupe sanguin |
| Medical_Condition | string | Pathologie (Cancer, Diabetes...) |
| Date_of_Admission | date | Date d'admission |
| Doctor | string | Médecin |
| Hospital | string | Hôpital |
| Insurance_Provider | string | Assureur |
| Billing_Amount | float | Montant facturé |
| Room_Number | int | Chambre |
| Admission_Type | string | Urgent, Emergency, Elective |
| Discharge_Date | date | Date de sortie |
| Medication | string | Médicament prescrit |
| Test_Results | string | Normal, Abnormal, Inconclusive |

Index créés :
- `idx_name` sur Name
- `idx_medical_condition` sur Medical_Condition
- `idx_age_gender` composé sur Age + Gender

## Authentification et rôles

Les users sont créés par `init-mongo.js` au premier démarrage :

- **admin** : root mongo (maintenance)
- **appuser** : readWrite sur healthcare (c'est celui utilisé par le loader)
- **readOnlyUser** : read seul sur healthcare (pour le reporting)
- **supportUser** : read + readWrite + dbAdmin (support technique)
- **adminUser** : readWrite + dbAdmin + clusterAdmin (supervision)

L'idée c'est le principe du moindre privilège : le loader utilise seulement appuser qui a juste readWrite.

## Architecture Docker

```
docker-compose.yml
├── mongo (mongo:7)
│   ├── volume mongodb_data (persistance)
│   ├── volume ./initdb (script init)
│   └── healthcheck (ping)
│
└── loader (python:3.11-slim)
    ├── depends_on: mongo (healthy)
    └── volume ./data (CSV, read-only)
```

Le flow :
1. Mongo démarre et exécute init-mongo.js
2. Le healthcheck vérifie que mongo répond
3. Une fois healthy, le loader se lance
4. Il fait la migration puis s'arrête

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

5 tests avec mongomock (pas besoin de mongo) :
- log() affiche bien le prefix
- sanitize_columns nettoie les noms
- try_parse_dates convertit les dates
- main() insère et déduplique correctement
- main() quitte en erreur si le CSV manque

## Commandes utiles

```bash
docker compose down             # arrêter
docker compose down -v          # arrêter + supprimer les données
docker compose build --no-cache # rebuild
docker compose run --rm loader  # relancer juste le loader
```

Voir aussi `cheat_sheet_mongo.md` pour les commandes mongosh.

## Sauvegarde

```bash
docker exec -it mongodb mongodump --db healthcare --out /backup
docker cp mongodb:/backup ./backup
```
