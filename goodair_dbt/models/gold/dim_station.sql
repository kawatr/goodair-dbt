-- dim_station : référentiel des stations
{{ config(materialized='table') }}

SELECT DISTINCT
    v.id                AS station_id,
    v.slug_aqicn        AS station_slug,
    v.nom               AS station_nom,
    v.latitude,
    v.longitude,
    a.station_nom       AS station_nom_aqicn,
    a.station_url       AS station_url,
    a.station_timezone  AS timezone
FROM {{ source('silver', 'ville') }} v
LEFT JOIN {{ source('silver', 'mesure_air_aqicn') }} a
    ON v.id = a.ville_id
WHERE v.actif = TRUE
