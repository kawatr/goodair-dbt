-- dim_pollutant : liste des indicateurs mesurés
{{ config(materialized='table') }}

SELECT * FROM (VALUES
    ('aqi',    'AQI Global',    'Index',  'AQICN'),
    ('pm25',   'PM2.5',         'µg/m³',  'AQICN'),
    ('pm10',   'PM10',          'µg/m³',  'AQICN'),
    ('no2',    'NO2',           'µg/m³',  'AQICN'),
    ('o3',     'Ozone',         'µg/m³',  'AQICN'),
    ('co',     'CO',            'µg/m³',  'AQICN'),
    ('so2',    'SO2',           'µg/m³',  'AQICN'),
    ('aqi_owm','AQI OWM',       '1-5',    'OWM'),
    ('pm2_5',  'PM2.5 OWM',    'µg/m³',  'OWM'),
    ('no2_owm','NO2 OWM',       'µg/m³',  'OWM'),
    ('o3_owm', 'Ozone OWM',     'µg/m³',  'OWM'),
    ('nh3',    'NH3',           'µg/m³',  'OWM')
) AS t(polluant_id, polluant_nom, unite, source)
