-- dim_city : référentiel des villes
{{ config(materialized='table') }}

SELECT
    id          AS city_id,
    nom         AS city_nom,
    slug_aqicn  AS city_slug,
    latitude,
    longitude
FROM {{ source('silver', 'ville') }}
WHERE actif = TRUE
