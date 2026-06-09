"""
GoodAir — ML Random Forest — Prévision Température T+1h
========================================================
Source  : PostgreSQL Silver (public.mesure_air_aqicn)
Sortie  : PostgreSQL Gold (gold_gold.ml_predictions_temperature)
"""

import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sqlalchemy import create_engine, text
import warnings
warnings.filterwarnings("ignore")

# ── Config PostgreSQL ─────────────────────────────────────────────────────────
PG_HOST = os.environ.get("POSTGRES_HOST", "goodair-pg-26074.postgres.database.azure.com")
PG_USER = os.environ.get("POSTGRES_USER", "goodairadmin")
PG_PASS = os.environ.get("POSTGRES_PASSWORD", "GoodAir_Azure_2026!")
PG_DB   = "goodairdb"
PG_PORT = 5432

ENGINE = create_engine(
    f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    "?sslmode=require"
)

print("=" * 60)
print("GoodAir — Random Forest — Prévision Température T+1h")
print("=" * 60)

# ── Chargement depuis PostgreSQL Silver ───────────────────────────────────────
print("\n Chargement des données depuis PostgreSQL Silver...")

df = pd.read_sql("""
    SELECT
        a.ville_id,
        a.collecte_le AS mesure_le,
        a.temperature,
        a.humidite,
        a.pression,
        a.vent
    FROM public.mesure_air_aqicn a
    WHERE a.temperature IS NOT NULL
      AND a.humidite    IS NOT NULL
      AND a.pression    IS NOT NULL
    ORDER BY a.ville_id, a.collecte_le
""", ENGINE)

print(f"  {len(df):,} mesures chargées pour {df['ville_id'].nunique()} villes")

if len(df) < 100:
    print("  Pas assez de données — relance ce script plus tard")
    exit()

# ── Feature engineering ───────────────────────────────────────────────────────
df["mesure_le"] = pd.to_datetime(df["mesure_le"])
df = df.sort_values(["ville_id", "mesure_le"]).reset_index(drop=True)

df["heure"]        = df["mesure_le"].dt.hour
df["jour_semaine"] = df["mesure_le"].dt.dayofweek
df["mois"]         = df["mesure_le"].dt.month
df["jour_annee"]   = df["mesure_le"].dt.dayofyear
df["heure_sin"]    = np.sin(2 * np.pi * df["heure"] / 24)
df["heure_cos"]    = np.cos(2 * np.pi * df["heure"] / 24)
df["mois_sin"]     = np.sin(2 * np.pi * df["mois"] / 12)
df["mois_cos"]     = np.cos(2 * np.pi * df["mois"] / 12)

df["temp_lag_1h"]  = df.groupby("ville_id")["temperature"].shift(1)
df["temp_lag_2h"]  = df.groupby("ville_id")["temperature"].shift(2)
df["temp_lag_3h"]  = df.groupby("ville_id")["temperature"].shift(3)
df["temp_lag_6h"]  = df.groupby("ville_id")["temperature"].shift(6)
df["temp_lag_12h"] = df.groupby("ville_id")["temperature"].shift(12)
df["temp_lag_24h"] = df.groupby("ville_id")["temperature"].shift(24)
df["temp_rolling_mean_24h"] = (df.groupby("ville_id")["temperature"]
                                 .transform(lambda x: x.shift(1).rolling(24).mean()))
df["temp_rolling_std_24h"]  = (df.groupby("ville_id")["temperature"]
                                 .transform(lambda x: x.shift(1).rolling(24).std()))

FEATURES = [
    "heure_sin", "heure_cos", "mois_sin", "mois_cos",
    "jour_semaine", "jour_annee", "ville_id",
    "temp_lag_1h", "temp_lag_2h", "temp_lag_3h",
    "temp_lag_6h", "temp_lag_12h", "temp_lag_24h",
    "temp_rolling_mean_24h", "temp_rolling_std_24h",
    "humidite", "pression", "vent",
]
CIBLE = "temperature"

df = df.dropna(subset=FEATURES + [CIBLE]).reset_index(drop=True)

# ── Split temporel 80/20 ──────────────────────────────────────────────────────
split_date = df["mesure_le"].quantile(0.8)
train_mask = df["mesure_le"] <= split_date
test_mask  = df["mesure_le"] >  split_date

X_train = df.loc[train_mask, FEATURES]
X_test  = df.loc[test_mask,  FEATURES]
y_train = df.loc[train_mask, CIBLE]
y_test  = df.loc[test_mask,  CIBLE]
dates_test = df.loc[test_mask, "mesure_le"]

print(f"  Train : {len(X_train):,} lignes  |  Test : {len(X_test):,} lignes")

# ── Entraînement Random Forest ────────────────────────────────────────────────
print("\n Entraînement RandomForest...")
model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

# ── Métriques ─────────────────────────────────────────────────────────────────
def mape(y_true, y_pred):
    mask = y_true != 0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

mae      = mean_absolute_error(y_test, y_pred)
rmse     = np.sqrt(mean_squared_error(y_test, y_pred))
mape_val = mape(y_test.values, y_pred)
r2       = r2_score(y_test, y_pred)
erreurs  = y_test.values - y_pred

print("\n" + "="*45)
print("  RÉSULTATS — RandomForest T+1h")
print("="*45)
print(f"  R²   = {r2:.4f}")
print(f"  MAE  = {mae:.4f} °C")
print(f"  RMSE = {rmse:.4f} °C")
print(f"  MAPE = {mape_val:.4f} %")
print("="*45)

# ── Export PostgreSQL Gold ────────────────────────────────────────────────────
print("\n Écriture dans gold_gold.ml_predictions_temperature...")

df_export = pd.DataFrame({
    "mesure_le":    dates_test.values,
    "ville_id":     df.loc[test_mask, "ville_id"].values,
    "temp_reelle":  y_test.values,
    "temp_predite": y_pred,
    "erreur":       erreurs,
})

with ENGINE.connect() as conn:
    # Créer le schéma gold_gold si besoin
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold_gold;"))

    # Créer la table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS gold_gold.ml_predictions_temperature (
            id            SERIAL PRIMARY KEY,
            mesure_le     TIMESTAMP NOT NULL,
            ville_id      INTEGER   NOT NULL,
            temp_reelle   FLOAT,
            temp_predite  FLOAT,
            erreur        FLOAT,
            inserted_at   TIMESTAMP DEFAULT NOW()
        );
    """))

    # Vider la table avant réinsertion (évite les doublons)
    conn.execute(text("TRUNCATE TABLE gold_gold.ml_predictions_temperature;"))
    conn.commit()
    print("  Table gold_gold.ml_predictions_temperature prête")

df_export.to_sql(
    name="ml_predictions_temperature",
    schema="gold_gold",
    con=ENGINE,
    if_exists="append",
    index=False,
    method="multi",
    chunksize=1000
)

print(f"  {len(df_export):,} prédictions insérées dans gold_gold")
print("\n GoodAir ML Random Forest terminé !")
print("="*60)