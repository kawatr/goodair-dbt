-- dim_time : décomposition temporelle
{{ config(materialized='table') }}

SELECT DISTINCT
    collecte_le                                         AS datetime_utc,
    DATE(collecte_le)                                   AS date,
    EXTRACT(YEAR  FROM collecte_le)::INT                AS annee,
    EXTRACT(MONTH FROM collecte_le)::INT                AS mois,
    EXTRACT(DAY   FROM collecte_le)::INT                AS jour,
    EXTRACT(HOUR  FROM collecte_le)::INT                AS heure,
    EXTRACT(WEEK  FROM collecte_le)::INT                AS semaine,
    TO_CHAR(collecte_le, 'Day')                         AS jour_semaine
FROM {{ source('silver', 'mesure_air_aqicn') }}
WHERE collecte_le IS NOT NULL
