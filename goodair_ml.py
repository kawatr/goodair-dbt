"""
GoodAir — Machine Learning Pipeline
=====================================
ML 1 : Détection d'anomalies (Isolation Forest)
ML 2 : Prévision PM2.5 et AQI (Prophet)
ML 3 : Clustering des villes (K-Means)

Les résultats sont écrits dans PostgreSQL pour Power BI.
"""

import pandas as pd
import numpy as np
import psycopg2
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ── Config PostgreSQL ─────────────────────────────────────────────────────────
PG_HOST = "goodair-pg-26074.postgres.database.azure.com"
PG_USER = "goodairadmin"
PG_PASS = "GoodAir_Azure_2026!"
PG_DB   = "goodairdb"
PG_PORT = 5432

ENGINE = create_engine(
    f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    f"?sslmode=require"
)

def get_conn():
    return psycopg2.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER,
        password=PG_PASS, port=PG_PORT, sslmode="require"
    )

print("=" * 60)
print("GoodAir ML Pipeline")
print("=" * 60)

# ── Chargement des données ────────────────────────────────────────────────────
print("\n📊 Chargement des données depuis PostgreSQL...")

df = pd.read_sql("""
    SELECT 
        v.nom       AS ville,
        v.slug_aqicn AS slug,
        a.collecte_le,
        a.aqi_global,
        a.pm25,
        a.pm10,
        a.no2,
        a.o3,
        a.temperature,
        a.humidite
    FROM mesure_air_aqicn a
    JOIN ville v ON v.id = a.ville_id
    WHERE a.aqi_global IS NOT NULL
    ORDER BY a.collecte_le
""", ENGINE)

print(f"  ✓ {len(df)} mesures chargées pour {df['ville'].nunique()} villes")

if len(df) == 0:
    print("  ⚠ Pas encore de données — relance ce script après 20h15")
    exit()

# ════════════════════════════════════════════════════════════════════════════
# ML 1 — DÉTECTION D'ANOMALIES (Isolation Forest)
# ════════════════════════════════════════════════════════════════════════════
print("\n🔍 ML 1 : Détection d'anomalies (Isolation Forest)...")

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

features = ['aqi_global', 'pm25', 'pm10', 'no2', 'o3']
df_ml = df[features].dropna()

if len(df_ml) > 10:
    scaler = StandardScaler()
    X = scaler.fit_transform(df_ml)

    iso = IsolationForest(contamination=0.1, random_state=42, n_estimators=100)
    df.loc[df_ml.index, 'anomalie_score'] = iso.fit_predict(X)
    df.loc[df_ml.index, 'anomalie_flag'] = df.loc[df_ml.index, 'anomalie_score'] == -1

    nb_anomalies = df['anomalie_flag'].sum()
    print(f"  ✓ {nb_anomalies} anomalies détectées sur {len(df_ml)} mesures")

    # Sauvegarde dans PostgreSQL
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS ml_anomalies")
    cur.execute("""
        CREATE TABLE ml_anomalies (
            id          SERIAL PRIMARY KEY,
            ville       VARCHAR NOT NULL,
            collecte_le TIMESTAMP NOT NULL,
            aqi_global  NUMERIC,
            pm25        NUMERIC,
            pm10        NUMERIC,
            no2         NUMERIC,
            o3          NUMERIC,
            score       INTEGER,
            est_anomalie BOOLEAN,
            cree_le     TIMESTAMP DEFAULT NOW()
        )
    """)
    anomalies = df[df['anomalie_flag'] == True]
    for _, row in anomalies.iterrows():
        cur.execute("""
            INSERT INTO ml_anomalies 
                (ville, collecte_le, aqi_global, pm25, pm10, no2, o3, score, est_anomalie)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            row['ville'], row['collecte_le'],
            row.get('aqi_global'), row.get('pm25'),
            row.get('pm10'), row.get('no2'), row.get('o3'),
            int(row['anomalie_score']), bool(row['anomalie_flag'])
        ))
    conn.commit()
    cur.close()
    conn.close()
    print(f"  ✓ Anomalies sauvegardées dans PostgreSQL (table ml_anomalies)")
else:
    print("  ⚠ Pas assez de données pour Isolation Forest")

# ════════════════════════════════════════════════════════════════════════════
# ML 2 — PRÉVISION PM2.5 ET AQI (Prophet)
# ════════════════════════════════════════════════════════════════════════════
print("\n🔮 ML 2 : Prévision PM2.5 et AQI (Prophet)...")

from prophet import Prophet

conn = get_conn()
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS ml_predictions")
cur.execute("""
    CREATE TABLE ml_predictions (
        id          SERIAL PRIMARY KEY,
        ville       VARCHAR NOT NULL,
        mesure      VARCHAR NOT NULL,
        datetime_utc TIMESTAMP NOT NULL,
        valeur_pred  NUMERIC,
        valeur_min   NUMERIC,
        valeur_max   NUMERIC,
        type        VARCHAR NOT NULL,
        cree_le     TIMESTAMP DEFAULT NOW()
    )
""")
conn.commit()

villes_top = df.groupby('ville')['aqi_global'].count().nlargest(5).index.tolist()

for ville in villes_top:
    df_ville = df[df['ville'] == ville].copy()

    for mesure in ['aqi_global', 'pm25']:
        df_prophet = df_ville[['collecte_le', mesure]].dropna()
        df_prophet.columns = ['ds', 'y']
        df_prophet = df_prophet.sort_values('ds')

        if len(df_prophet) < 5:
            continue

        try:
            model = Prophet(
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.05
            )
            model.fit(df_prophet)

            future = model.make_future_dataframe(periods=24, freq='h')
            forecast = model.predict(future)

            # Sauvegarde historique + prédictions
            for _, row in forecast.iterrows():
                type_val = 'historique' if row['ds'] <= df_prophet['ds'].max() else 'prediction'
                cur.execute("""
                    INSERT INTO ml_predictions
                        (ville, mesure, datetime_utc, valeur_pred, valeur_min, valeur_max, type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    ville, mesure, row['ds'],
                    max(0, round(float(row['yhat']), 2)),
                    max(0, round(float(row['yhat_lower']), 2)),
                    max(0, round(float(row['yhat_upper']), 2)),
                    type_val
                ))

            print(f"  ✓ {ville} — {mesure} : prévisions 24h calculées")
        except Exception as e:
            print(f"  ✗ {ville} — {mesure} : {e}")

conn.commit()
cur.close()
conn.close()
print("  ✓ Prédictions sauvegardées dans PostgreSQL (table ml_predictions)")

# ════════════════════════════════════════════════════════════════════════════
# ML 3 — CLUSTERING DES VILLES (K-Means)
# ════════════════════════════════════════════════════════════════════════════
print("\n🗺️  ML 3 : Clustering des villes (K-Means)...")

from sklearn.cluster import KMeans

df_cluster = df.groupby('ville')[['aqi_global', 'pm25', 'pm10', 'no2', 'o3']].mean().dropna()

if len(df_cluster) >= 3:
    n_clusters = min(4, len(df_cluster))
    scaler2 = StandardScaler()
    X2 = scaler2.fit_transform(df_cluster)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df_cluster['cluster'] = kmeans.fit_predict(X2)

    labels = {0: 'Air pur', 1: 'Pollution modérée', 2: 'Pollution élevée', 3: 'Pollution critique'}

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS ml_clusters")
    cur.execute("""
        CREATE TABLE ml_clusters (
            id          SERIAL PRIMARY KEY,
            ville       VARCHAR NOT NULL,
            cluster_id  INTEGER NOT NULL,
            cluster_nom VARCHAR NOT NULL,
            aqi_moyen   NUMERIC,
            pm25_moyen  NUMERIC,
            pm10_moyen  NUMERIC,
            no2_moyen   NUMERIC,
            o3_moyen    NUMERIC,
            cree_le     TIMESTAMP DEFAULT NOW()
        )
    """)
    for ville, row in df_cluster.iterrows():
        cluster_id = int(row['cluster'])
        cur.execute("""
            INSERT INTO ml_clusters
                (ville, cluster_id, cluster_nom, aqi_moyen, pm25_moyen, pm10_moyen, no2_moyen, o3_moyen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            ville, cluster_id,
            labels.get(cluster_id, f'Groupe {cluster_id}'),
            round(float(row['aqi_global']), 2) if not pd.isna(row['aqi_global']) else None,
            round(float(row['pm25']), 2) if not pd.isna(row['pm25']) else None,
            round(float(row['pm10']), 2) if not pd.isna(row['pm10']) else None,
            round(float(row['no2']), 2) if not pd.isna(row['no2']) else None,
            round(float(row['o3']), 2) if not pd.isna(row['o3']) else None,
        ))
        print(f"  ✓ {ville} → Cluster {cluster_id} ({labels.get(cluster_id, 'Groupe')})")
    conn.commit()
    cur.close()
    conn.close()
    print("  ✓ Clusters sauvegardés dans PostgreSQL (table ml_clusters)")
else:
    print("  ⚠ Pas assez de villes pour le clustering")

print("\n" + "=" * 60)
print("✅ GoodAir ML Pipeline terminé !")
print("Tables créées dans PostgreSQL :")
print("  - ml_anomalies   : anomalies détectées par Isolation Forest")
print("  - ml_predictions : prévisions PM2.5 et AQI par Prophet")
print("  - ml_clusters    : clustering K-Means des villes")
print("=" * 60)