-- fact_air_quality : mesures horaires d'AQI par station
{{ config(materialized='table') }}

SELECT
    -- Clés de dimension
    a.ville_id                          AS station_id,
    a.ville_id                          AS city_id,
    a.collecte_le                       AS datetime_utc,

    -- Mesures AQICN
    a.aqi_global,
    a.polluant_dominant,
    a.pm25,
    a.pm10,
    a.no2,
    a.o3,
    a.co,
    a.so2,
    a.temperature                       AS temp_aqicn,
    a.humidite                          AS humidite_aqicn,
    a.pression                          AS pression_aqicn,
    a.vent                              AS vent_aqicn,

    -- Mesures météo OWM
    m.temperature,
    m.temperature_ressentie,
    m.temp_min,
    m.temp_max,
    m.pression_hpa,
    m.humidite_pct,
    m.vitesse_vent,
    m.direction_vent,
    m.couverture_nuages,
    m.visibilite_m,
    m.condition_libelle,
    m.condition_desc,

    -- Mesures pollution OWM
    p.aqi_owm,
    p.co                                AS co_owm,
    p.no,
    p.no2                               AS no2_owm,
    p.o3                                AS o3_owm,
    p.so2                               AS so2_owm,
    p.pm2_5,
    p.pm10                              AS pm10_owm,
    p.nh3

FROM {{ source('silver', 'mesure_air_aqicn') }} a
LEFT JOIN {{ source('silver', 'mesure_meteo') }} m
    ON a.ville_id = m.ville_id
    AND DATE_TRUNC('hour', a.collecte_le) = DATE_TRUNC('hour', m.collecte_le)
LEFT JOIN {{ source('silver', 'mesure_pollution_owm') }} p
    ON a.ville_id = p.ville_id
    AND DATE_TRUNC('hour', a.collecte_le) = DATE_TRUNC('hour', p.collecte_le)
WHERE a.ville_id IS NOT NULL
