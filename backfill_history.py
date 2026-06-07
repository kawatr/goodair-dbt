"""
GoodAir — Extraction historique horaire des données -> CSV (complet)

  AQICN               -> station_nom, url, idx, timezone, attributions
  OWM /history        -> polluants horaires (pm25, pm10, no2, o3, co, so2, aqi)
  Open-Meteo /archive -> météo horaire (temperature, humidite, pression, vent)

Usage :
  pip install requests
  python backfill_history.py
"""

import csv, json, os, time, requests
from datetime import datetime, timezone, date, timedelta



DATE_DEBUT  = "2026-03-01"
DATE_FIN    = "2026-05-30"
FICHIER_CSV = "goodair_historique_complet.csv"

AQICN_TOKEN = "7e7c276e0b8651327d4bd3993857268d0f6a4bb8"
OWM_API_KEY = "651e6c14dbbb2fde75c28d5880f652bf"

# 30 VILLES FRANÇAISES 
VILLES = [
    ( 1, "Paris",            "paris",              48.8566,  2.3522),
    ( 2, "Lyon",             "lyon",               45.7640,  4.8357),
    ( 3, "Marseille",        "marseille",          43.2965,  5.3698),
    ( 4, "Toulouse",         "toulouse",           43.6047,  1.4442),
    ( 5, "Bordeaux",         "bordeaux",           44.8378, -0.5792),
    ( 6, "Lille",            "lille",              50.6292,  3.0573),
    ( 7, "Strasbourg",       "strasbourg",         48.5734,  7.7521),
    ( 8, "Nice",             "nice",               43.7102,  7.2620),
    ( 9, "Nantes",           "nantes",             47.2184, -1.5536),
    (10, "Grenoble",         "grenoble",           45.1885,  5.7245),
    (11, "Rennes",           "rennes",             48.1173, -1.6778),
    (12, "Reims",            "reims",              49.2583,  4.0317),
    (13, "Le Havre",         "le-havre",           49.4944,  0.1079),
    (14, "Saint-Etienne",    "saint-etienne",      45.4347,  4.3900),
    (15, "Toulon",           "toulon",             43.1242,  5.9280),
    (16, "Angers",           "angers",             47.4784, -0.5632),
    (17, "Dijon",            "dijon",              47.3220,  5.0415),
    (18, "Brest",            "brest",              48.3905, -4.4860),
    (19, "Nimes",            "nimes",              43.8367,  4.3601),
    (20, "Aix-en-Provence",  "aix-en-provence",    43.5297,  5.4474),
    (21, "Clermont-Ferrand", "clermont-ferrand",   45.7772,  3.0870),
    (22, "Tours",            "tours",              47.3941,  0.6848),
    (23, "Amiens",           "amiens",             49.8942,  2.2957),
    (24, "Metz",             "metz",               49.1193,  6.1757),
    (25, "Montpellier",      "montpellier",        43.6108,  3.8767),
    (26, "Rouen",            "rouen",              49.4432,  1.0999),
    (27, "Caen",             "caen",               49.1829, -0.3707),
    (28, "Nancy",            "nancy",              48.6921,  6.1844),
    (29, "Perpignan",        "perpignan",          42.6887,  2.8948),
    (30, "Orleans",          "orleans",            47.9029,  1.9039),
]

COLONNES = [
    "id", "ville_id", "collecte_le", "mesure_le",
    "station_timezone", "aqi_global",
    "pm25", "pm10", "no2", "o3", "co", "so2",
    "temperature", "humidite", "pression", "vent",
    "polluant_dominant", "station_nom", "station_url",
    "station_idx", "attributions",
]

# Validation des données
PLAGES = {
    "co":  (0, 50000), "no2": (0, 2000), "o3":   (0,  500),
    "so2": (0,  1000), "pm25":(0,  500), "pm10": (0,  600),
    "t":   (-60,   60), "h":  (0,  100), "p":  (870, 1084),
    "w":   (0,    200),
}

def clean(cle, val):
    if val is None: return ""
    try: f = float(val)
    except (TypeError, ValueError): return ""
    if f != f: return ""
    p = PLAGES.get(cle)
    if p and not (p[0] <= f <= p[1]): return ""
    return int(f) if f == int(f) else round(f, 2)

# SOURCE 1 — AQICN : métadonnées station (1 appel / ville)
def fetch_metadata_aqicn():
    print("\n━━━ Étape 1/3 — AQICN : métadonnées station ━━━")
    meta = {}
    for ville_id, nom, slug, lat, lon in VILLES:
        try:
            r = requests.get(
                f"https://api.waqi.info/feed/{slug}/?token={AQICN_TOKEN}",
                timeout=10
            )
            d = r.json()
            if d.get("status") != "ok":
                meta[ville_id] = {}
                print(f"  ⚠  {nom} : statut={d.get('status')}")
                continue
            raw   = d["data"]
            city  = raw.get("city", {})
            attrs = raw.get("attributions", [])
            meta[ville_id] = {
                "station_nom":      city.get("name", nom),
                "station_url":      city.get("url", ""),
                "station_idx":      raw.get("idx", ""),
                "station_timezone": city.get("timezone", ""),
                "attributions": json.dumps(
                    [{"nom": a.get("name",""), "url": a.get("url","")} for a in attrs],
                    ensure_ascii=False
                ) if attrs else "",
            }
            print(f"  ✓  {nom}")
        except Exception as e:
            meta[ville_id] = {}
            print(f"  ✗  {nom} : {e}")
        time.sleep(0.4)
    print(f"  → {sum(1 for m in meta.values() if m)}/{len(VILLES)} stations ok")
    return meta

# SOURCE 2 — OWM /air_pollution/history : polluants horaires (1 appel / ville)
def fetch_pollution_owm(lat, lon, ts_debut, ts_fin):
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/air_pollution/history"
            f"?lat={lat}&lon={lon}&start={ts_debut}&end={ts_fin}&appid={OWM_API_KEY}",
            timeout=30
        )
        r.raise_for_status()
        return r.json().get("list", [])
    except Exception as e:
        print(f"    [OWM] erreur : {e}")
        return []

def parser_pollution(items):
    """
    Retourne un dict { "YYYY-MM-DD HH:00:00" → dict de valeurs }.
    Clé = heure arrondie à la minute 00 pour jointure avec Open-Meteo.
    """
    result = {}
    for item in items:
        if not item.get("dt"): continue
        comp = item.get("components", {})
        ts   = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
        cle  = ts.strftime("%Y-%m-%d %H:00:00")

        polluants = {
            "pm25": comp.get("pm2_5") or 0,
            "pm10": comp.get("pm10")  or 0,
            "no2":  comp.get("no2")   or 0,
            "o3":   comp.get("o3")    or 0,
            "so2":  comp.get("so2")   or 0,
            "co":  (comp.get("co")    or 0) / 100,
        }
        polluant_dominant = max(polluants, key=polluants.get)
        aqi_owm = item.get("main", {}).get("aqi")

        result[cle] = {
            "mesure_le":        cle,
            "aqi_global":       {1:25,2:75,3:100,4:150,5:200}.get(aqi_owm, ""),
            "pm25":             clean("pm25", comp.get("pm2_5")),
            "pm10":             clean("pm10", comp.get("pm10")),
            "no2":              clean("no2",  comp.get("no2")),
            "o3":               clean("o3",   comp.get("o3")),
            "co":               clean("co",   comp.get("co")),
            "so2":              clean("so2",  comp.get("so2")),
            "polluant_dominant":polluant_dominant,
        }
    return result

# SOURCE 3 — Open-Meteo/archive : météo horaire (1 appel / ville)
# Parce qu'on ne peut pas récupérer l'historique des données gratuitement avec l'API OWM
def fetch_meteo_openmeteo(lat, lon, date_debut, date_fin):
    try:
        r = requests.get(
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat}&longitude={lon}"
            f"&start_date={date_debut}&end_date={date_fin}"
            "&hourly=temperature_2m,relative_humidity_2m,"
            "surface_pressure,wind_speed_10m"
            "&timezone=UTC&wind_speed_unit=ms",
            timeout=30
        )
        r.raise_for_status()
        return r.json().get("hourly", {})
    except Exception as e:
        print(f"    [Open-Meteo] erreur : {e}")
        return {}

def parser_meteo(hourly):
    """
    Retourne un dict { "YYYY-MM-DD HH:00:00" → dict météo }.
    Même format de clé que parser_pollution → jointure directe.
    """
    result = {}
    times = hourly.get("time", [])
    temp  = hourly.get("temperature_2m",       [])
    hum   = hourly.get("relative_humidity_2m", [])
    pres  = hourly.get("surface_pressure",     [])
    wind  = hourly.get("wind_speed_10m",       [])

    for i, t in enumerate(times):
        # Open-Meteo renvoie "2026-03-01T00:00" → normaliser en "2026-03-01 00:00:00"
        cle = t.replace("T", " ") + ":00" if "T" in t else t
        result[cle] = {
            "temperature": clean("t", temp[i] if i < len(temp) else None),
            "humidite":    clean("h", hum[i]  if i < len(hum)  else None),
            "pression":    clean("p", pres[i] if i < len(pres) else None),
            "vent":        clean("w", wind[i] if i < len(wind) else None),
        }
    return result

# FUSION : jointure pollution + météo sur la clé heure
def fusionner(ville_id, meta, pollution, meteo, collecte_le_str):
    """
    Pour chaque heure présente dans pollution, on joint les données météo
    sur la même clé temporelle.
    """
    lignes = []
    for heure, pol in sorted(pollution.items()):
        met = meteo.get(heure, {})
        lignes.append({
            "id":               "",          # rempli à l'écriture
            "ville_id":         ville_id,
            "collecte_le":      collecte_le_str,
            "mesure_le":        pol["mesure_le"],
            "station_timezone": meta.get("station_timezone", ""),
            "aqi_global":       pol["aqi_global"],
            "pm25":             pol["pm25"],
            "pm10":             pol["pm10"],
            "no2":              pol["no2"],
            "o3":               pol["o3"],
            "co":               pol["co"],
            "so2":              pol["so2"],
            "temperature":      met.get("temperature", ""),
            "humidite":         met.get("humidite",    ""),
            "pression":         met.get("pression",    ""),
            "vent":             met.get("vent",        ""),
            "polluant_dominant":pol["polluant_dominant"],
            "station_nom":      meta.get("station_nom", ""),
            "station_url":      meta.get("station_url", ""),
            "station_idx":      meta.get("station_idx", ""),
            "attributions":     meta.get("attributions", ""),
        })
    return lignes


def main():
    date_debut = date.fromisoformat(DATE_DEBUT)
    date_fin   = date.fromisoformat(DATE_FIN)
    ts_debut   = int(datetime(date_debut.year, date_debut.month, date_debut.day,
                              0, 0, 0, tzinfo=timezone.utc).timestamp())
    ts_fin     = int(datetime(date_fin.year, date_fin.month, date_fin.day,
                              23, 59, 59, tzinfo=timezone.utc).timestamp())
    nb_jours   = (date_fin - date_debut).days + 1

    print("=" * 62)
    print("GoodAir — Extraction historique complète → CSV")
    print(f"  Période  : {DATE_DEBUT} → {DATE_FIN}  ({nb_jours} jours)")
    print(f"  Attendu  : ~{nb_jours * 24 * len(VILLES):,} lignes")
    print(f"  Fichier  : {FICHIER_CSV}")
    print(f"  Appels   : {len(VILLES)} AQICN  +  {len(VILLES)} OWM  +  {len(VILLES)} Open-Meteo")
    print("=" * 62)

    collecte_le_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Étape 1 : métadonnées AQICN 
    metadata = fetch_metadata_aqicn()

    # Étapes 2+3 : polluants OWM + météo Open-Meteo + écriture CSV
    print("\n━━━ Étapes 2/3 + 3/3 — OWM & Open-Meteo → CSV ━━━")

    with open(FICHIER_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLONNES, delimiter=";")
        writer.writeheader()

        row_id       = 1
        total_lignes = 0

        for ville_id, nom, slug, lat, lon in VILLES:
            print(f"  → {nom}...", end=" ", flush=True)

            # OWM : polluants horaires
            items_owm = fetch_pollution_owm(lat, lon, ts_debut, ts_fin)
            pollution = parser_pollution(items_owm)

            # Open-Meteo : météo horaire (même plage)
            hourly    = fetch_meteo_openmeteo(lat, lon, DATE_DEBUT, DATE_FIN)
            meteo     = parser_meteo(hourly)

            if not pollution:
                print("⚠  aucune donnée pollution")
                time.sleep(0.5)
                continue

            # Fusion sur la clé heure
            lignes = fusionner(
                ville_id, metadata.get(ville_id, {}),
                pollution, meteo, collecte_le_str
            )

            # Écriture CSV
            for ligne in lignes:
                ligne["id"] = row_id
                writer.writerow(ligne)
                row_id += 1

            total_lignes += len(lignes)

            # Taux de complétion météo
            meteo_ok = sum(
                1 for l in lignes if l["temperature"] != ""
            )
            pct = round(meteo_ok / len(lignes) * 100) if lignes else 0

            h_debut = lignes[0]["mesure_le"]  if lignes else "?"
            h_fin   = lignes[-1]["mesure_le"] if lignes else "?"
            print(
                f"✓  {len(lignes):>5} h  |  "
                f"météo {pct}%  |  "
                f"{h_debut} → {h_fin}"
            )

            time.sleep(0.5)

    # Bilan  - affichage
    taille_ko = os.path.getsize(FICHIER_CSV) / 1024
    print()
    print("=" * 62)
    print("EXPORT TERMINÉ")
    print(f"Fichier    : {FICHIER_CSV}")
    print(f"Lignes     : {total_lignes:,}  (hors en-tête)")
    print(f"Taille     : {taille_ko:.0f} Ko  ({taille_ko/1024:.1f} Mo)")
    print(f"Période    : {DATE_DEBUT} → {DATE_FIN}")
    print()
    print("Colonnes   :")
    print("polluants   : aqi_global, pm25, pm10, no2, o3, co, so2")
    print("météo       : temperature, humidite, pression, vent")
    print("station     : nom, url, idx, timezone, attributions")
    print("=" * 62)

if __name__ == "__main__":
    main()
