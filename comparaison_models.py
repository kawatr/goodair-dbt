import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor
from catboost import CatBoostRegressor
import warnings
warnings.filterwarnings("ignore")

# Chargement
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

# Lag +1h (horizon 1 = prédire l'heure suivante)
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
print(f"Lignes disponibles : {len(df):,}")

# Split temporelle - train, test
split_date = df["mesure_le"].quantile(0.8)
train_mask = df["mesure_le"] <= split_date
test_mask  = df["mesure_le"] >  split_date

X_train = df.loc[train_mask, FEATURES]
X_test  = df.loc[test_mask,  FEATURES]
y_train = df.loc[train_mask, CIBLE]
y_test  = df.loc[test_mask,  CIBLE]

print(f"Split : {split_date.date()}")
print(f"Train : {len(X_train):,} lignes  |  Test : {len(X_test):,} lignes\n")

# Entrainement et métriques
def mape(y_true, y_pred):
    mask = y_true != 0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

modeles = {
    "RandomForest": RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1),
    "XGBoost":      XGBRegressor(n_estimators=200, learning_rate=0.05,
                                  max_depth=6, random_state=42, verbosity=0),
    "CatBoost":     CatBoostRegressor(iterations=200, learning_rate=0.05,
                                       depth=6, random_state=42, verbose=0),
}

resultats = []

for nom, modele in modeles.items():
    modele.fit(X_train, y_train)
    y_pred = modele.predict(X_test)
    resultats.append({
        "Modèle": nom,
        "MAE":    round(mean_absolute_error(y_test, y_pred), 4),
        "RMSE":   round(np.sqrt(mean_squared_error(y_test, y_pred)), 4),
        "MAPE":   round(mape(y_test.values, y_pred), 4),
        "R²":     round(r2_score(y_test, y_pred), 4),
    })

# RÉSULTAT
df_res = pd.DataFrame(resultats).set_index("Modèle")

print("Métriques pour le choix de modèle — Prévision T+1h \n")
print(df_res.to_string())
