# GoodAir — Pipeline Big Data Azure

Projet MSPR Bloc 3 — Pipeline de collecte, transformation et analyse de la qualité de l'air pour 30 villes françaises.

## Architecture

```
AQICN + OpenWeatherMap (APIs)
        ↓
Azure Functions Python — Extraction (H:00)
        ↓
ADLS Gen2 — Data Lake Bronze (JSON bruts)
        ↓
Azure Functions Python — Transformation (H:15)
        ↓
ADLS Gen2 — Data Lake Silver (JSON propres) + PostgreSQL Silver
        ↓
dbt Core — GitHub Actions (H:30)
        ↓
PostgreSQL Gold (modèle en étoile)
        ↓
goodair_ml.py — GitHub Actions (H:35)
        ↓
PostgreSQL ML (anomalies + prévisions + clusters)
        ↓
Power BI
```

## Prérequis

- Compte Azure avec crédit disponible (~15€/mois)
- Python 3.11
- Azure CLI (`az`)
- Azure Functions Core Tools (`func`)
- Terraform
- dbt Core (`pip install dbt-postgres`)
- Power BI Desktop

## Déploiement complet

### Étape 1 — Cloner les repos

```bash
git clone https://github.com/kawatr/goodair-dbt.git
git clone https://github.com/kawatr/goodair-functions.git
```

### Étape 2 — Se connecter à Azure

```bash
az login
```

### Étape 3 — Déployer l'infrastructure avec Terraform

```bash
cd goodair-dbt/terraform
terraform init
terraform apply \
  -var="aqicn_token=VOTRE_TOKEN_AQICN" \
  -var="owm_api_key=VOTRE_CLE_OWM"
```

Terraform crée automatiquement :
- Resource Group `goodair-rg` (France Central)
- ADLS Gen2 avec conteneurs bronze/silver/gold
- PostgreSQL Flexible Server B1ms
- Azure Functions (extraction + transformation)
- Azure Data Factory
- Azure Key Vault avec tous les secrets

Notez le `postgres_host` affiché à la fin du `terraform apply`.

### Étape 4 — Initialiser la base de données PostgreSQL

```bash
psql \
  -h <postgres_host> \
  -U goodairadmin \
  -d goodairdb \
  -f goodair-functions/init_database.sql
```

Mot de passe : `GoodAir_Azure_2026!`

### Étape 5 — Déployer les Azure Functions

**Extraction :**
```bash
cd goodair-functions
pip install -r requirements.txt
func azure functionapp publish goodair-extract-XXXXX
```

**Transformation :**
```bash
cd goodair-functions/goodair-transform
pip install -r requirements.txt
func azure functionapp publish goodair-transform-XXXXX
```

Remplacez `XXXXX` par le suffixe généré par Terraform.

### Étape 6 — Configurer GitHub Actions

Dans votre repo GitHub → **Settings** → **Secrets and variables** → **Actions** → ajouter :

| Secret | Valeur |
|--------|--------|
| `POSTGRES_HOST` | Votre host PostgreSQL |
| `POSTGRES_USER` | `goodairadmin` |
| `POSTGRES_PASSWORD` | `GoodAir_Azure_2026!` |

### Étape 7 — Configurer dbt

Créez le fichier `~/.dbt/profiles.yml` :

```yaml
goodair_dbt:
  target: dev
  outputs:
    dev:
      type: postgres
      host: <postgres_host>
      user: goodairadmin
      password: GoodAir_Azure_2026!
      port: 5432
      dbname: goodairdb
      schema: gold
      sslmode: require
```

Puis lancez dbt :

```bash
cd goodair-dbt
pip install dbt-postgres
dbt run
```

### Étape 8 — Lancer le pipeline ML

```bash
pip install psycopg2-binary pandas scikit-learn sqlalchemy xgboost catboost
python comparaison_models.py
python predict_temp.py
```

### Étape 9 — Connecter Power BI

1. Ouvrir Power BI Desktop
2. **Obtenir des données** → **Base de données PostgreSQL**
3. Remplir :
   - **Serveur** : votre `postgres_host`
   - **Base de données** : `goodairdb`
   - **Nom d'utilisateur** : `goodairadmin`
   - **Mot de passe** : `GoodAir_Azure_2026!`
4. Sélectionner les tables :
   - `gold_gold.fact_air_quality`
   - `gold_gold.dim_city`
   - `gold_gold.dim_station`
   - `gold_gold.dim_time`
   - `gold_gold.dim_pollutant`
   - `public.ml_predictions_temperature`
   - `public.ville`

## Pipeline automatique

Une fois déployé, le pipeline tourne automatiquement :

| Heure | Action | Outil |
|-------|--------|-------|
| H:00 | Extraction APIs → Bronze | Azure Functions |
| H:15 | Transformation Bronze → Silver + PostgreSQL | Azure Functions |
| H:30 | Transformation Silver → Gold | GitHub Actions (dbt) |
| H:35 | Prévision température Random Forest | GitHub Actions (Python) |

## Tables PostgreSQL

### Schéma public (Silver)
- `ville` — 30 villes françaises
- `mesure_air_aqicn` — données qualité air AQICN
- `mesure_meteo` — données météo OWM
- `mesure_pollution_owm` — données pollution OWM
- `ml_predictions_temperature` — prévisions température T+1h (Random Forest)
- `pipeline_log` — journal d'exécution du pipeline

### Schéma gold_gold (dbt)
- `fact_air_quality` — mesures horaires consolidées
- `dim_city` — dimension villes
- `dim_station` — dimension stations
- `dim_time` — dimension temps
- `dim_pollutant` — dimension polluants

## Machine Learning

| Algorithme | Objectif | Table |
|-----------|----------|-------|
| Random Forest | Prévision température T+1h (R²=0.957, MAE=0.96°C) | `ml_predictions_temperature` |

Trois algorithmes ont été comparés : Random Forest, XGBoost et CatBoost. Random Forest a été retenu pour ses performances supérieures avec un R²=0.957 et une MAE de 0.96°C sur les données de test.

## Sécurité

- Secrets API stockés dans Azure Key Vault
- Accès via Microsoft Entra ID + RBAC
- Données hébergées en France Central (RGPD)
- Connexions PostgreSQL en SSL mode require
- Aucun secret dans le code ni dans Git

## Coût estimé

| Service | Coût/mois |
|---------|-----------|
| PostgreSQL B1ms | ~7€ |
| Azure Functions (Consumption) | ~0€ |
| ADLS Gen2 | ~1€ |
| Azure Key Vault | ~1€ |
| Azure Data Factory | ~1€ |
| **Total** | **~10-15€** |

## APIs utilisées

- **AQICN** : https://aqicn.org/json-api/doc/ — qualité de l'air temps réel
- **OpenWeatherMap** : https://openweathermap.org/api — météo et pollution

## Villes couvertes

Paris, Lyon, Marseille, Toulouse, Bordeaux, Lille, Strasbourg, Nice, Nantes, Grenoble, Rennes, Reims, Le Havre, Saint-Etienne, Toulon, Angers, Dijon, Brest, Nimes, Aix-en-Provence, Clermont-Ferrand, Tours, Amiens, Metz, Montpellier, Rouen, Caen, Nancy, Perpignan, Orléans.
