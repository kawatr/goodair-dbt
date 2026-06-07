import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import warnings
warnings.filterwarnings("ignore")


df = pd.read_csv("goodair_nettoye.csv", sep=";", parse_dates=["mesure_le"])
df = df.drop(columns=["station_timezone"], errors="ignore")
df = df.sort_values(["ville_id", "mesure_le"]).reset_index(drop=True)


# Features 
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

# SPLIT Temporelle - train + test
split_date = df["mesure_le"].quantile(0.8)
train_mask = df["mesure_le"] <= split_date
test_mask  = df["mesure_le"] >  split_date

X_train = df.loc[train_mask, FEATURES]
X_test  = df.loc[test_mask,  FEATURES]
y_train = df.loc[train_mask, CIBLE]
y_test  = df.loc[test_mask,  CIBLE]
dates_test = df.loc[test_mask, "mesure_le"]

print(f"Train : {len(X_train):,} lignes  |  Test : {len(X_test):,} lignes")


# Entrainement
print("\n Entraînement RandomForest...")
model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

# Métriques - choix de modèle
def mape(y_true, y_pred):
    mask = y_true != 0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

mae  = mean_absolute_error(y_test, y_pred)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
mape_val = mape(y_test.values, y_pred)
r2   = r2_score(y_test, y_pred)

print("\n" + "="*45)
print("  RÉSULTATS — RandomForest T+1h")
print("="*45)
print(f"  R²   = {r2:.4f}")
print(f"  MAE  = {mae:.4f} °C")
print(f"  RMSE = {rmse:.4f} °C")
print(f"  MAPE = {mape_val:.4f} %")
print("="*45)


# Visualisation
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
fig.suptitle("GoodAir — RandomForest — Prévision Température T+1h",
             fontsize=13, fontweight="bold")

# 6.1 Réel vs Prédit (300 premières heures)
axes[0, 0].plot(dates_test.values[:300], y_test.values[:300],
                label="Réel", color="#2196F3", linewidth=1.2)
axes[0, 0].plot(dates_test.values[:300], y_pred[:300],
                label="Prédit", color="#F44336", linewidth=1.2, linestyle="--")
axes[0, 0].set_title("Réel vs Prédit (300 premières heures)")
axes[0, 0].set_xlabel("Date")
axes[0, 0].set_ylabel("Température (°C)")
axes[0, 0].legend()
axes[0, 0].tick_params(axis="x", rotation=30)

# 6.2 Scatter réel vs prédit
axes[0, 1].scatter(y_test, y_pred, alpha=0.3, color="#9C27B0", s=5)
axes[0, 1].plot([y_test.min(), y_test.max()],
                [y_test.min(), y_test.max()], "r--", linewidth=1.5)
axes[0, 1].set_title(f"Scatter Réel vs Prédit  (R²={r2:.4f})")
axes[0, 1].set_xlabel("Température réelle (°C)")
axes[0, 1].set_ylabel("Température prédite (°C)")

# 6.3 Distribution des erreurs
erreurs = y_test.values - y_pred
axes[1, 0].hist(erreurs, bins=60, color="#FF9800", edgecolor="white")
axes[1, 0].axvline(0, color="red", linestyle="--")
axes[1, 0].set_title(f"Distribution des erreurs  (MAE={mae:.2f}°C)")
axes[1, 0].set_xlabel("Erreur (°C)")
axes[1, 0].set_ylabel("Fréquence")

# 6.4 Feature importance Top 10
importances = pd.Series(model.feature_importances_, index=FEATURES)
importances.nlargest(10).sort_values().plot(
    kind="barh", ax=axes[1, 1], color="#4CAF50")
axes[1, 1].set_title("Top 10 Features importantes")

plt.tight_layout()
plt.savefig("goodair_rf_temperature.png", bbox_inches="tight", dpi=150)
plt.show()

# Eport la prédiction en csv
df_export = pd.DataFrame({
    "mesure_le":   dates_test.values,
    "ville_id":    df.loc[test_mask, "ville_id"].values,
    "temp_reelle": y_test.values,
    "temp_predite": y_pred,
    "erreur":      erreurs,
})
df_export.to_csv("predictions_temperature.csv", sep=";", index=False)
print(f"\nPrédictions exportées : predictions_temperature.csv")
print(f"Graphique sauvegardé  : goodair_rf_temperature.png")

# ============================================================
# EXPORT POSTGRESQL AZURE
# ============================================================
from sqlalchemy import create_engine, text


PG_HOST = "goodair-pg-26074.postgres.database.azure.com"
PG_USER = "goodairadmin"
PG_PASSWORD = "GoodAir_Azure_2026!"
PG_DB   = "goodairdb"
PG_PORT = 5432

print("\nConnexion PostgreSQL Azure...")

engine = create_engine(
    f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    "?sslmode=require"
)

# Créer la table si elle n'existe pas
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ml_predictions_temperature (
            id              SERIAL PRIMARY KEY,
            mesure_le       TIMESTAMP NOT NULL,
            ville_id        INTEGER NOT NULL,
            temp_reelle     FLOAT,
            temp_predite    FLOAT,
            erreur          FLOAT,
            inserted_at     TIMESTAMP DEFAULT NOW()
        );
    """))
    conn.commit()
    print("Table ml_predictions_temperature prête")

# Insérer les prédictions
df_export.to_sql(
    name="ml_predictions_temperature",
    con=engine,
    if_exists="append",   # append = ajoute sans écraser
    index=False,
    method="multi",       # insertion par batch (plus rapide)
    chunksize=1000
)

print(f"{len(df_export):,} prédictions insérées sur PostgreSQL Azure")
