{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_GEOLOCATION_ZIP') }}

with source_points as (
    select
        lpad(trim(geolocation_zip_code_prefix), 5, '0') as geolocation_zip_prefix,
        geolocation_lat,
        geolocation_lng,
        coalesce(nullif(upper(trim(geolocation_city)), ''), 'UNKNOWN') as geolocation_city,
        coalesce(nullif(upper(trim(geolocation_state)), ''), 'UNKNOWN') as geolocation_state,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        ingested_at,
        geolocation_lat between -90 and 90
            and geolocation_lng between -180 and 180 as coordinate_is_valid
    from {{ source('bronze_olist', 'geolocation') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
), aggregated as (
    select
        geolocation_zip_prefix,
        cast(round(avg(iff(coordinate_is_valid, geolocation_lat, null)), 18)
            as number(38, 18)) as centroid_latitude,
        cast(round(avg(iff(coordinate_is_valid, geolocation_lng, null)), 18)
            as number(38, 18)) as centroid_longitude,
        count(*) as source_point_count,
        count_if(coordinate_is_valid) as valid_coordinate_count,
        count_if(not coordinate_is_valid) as invalid_coordinate_count,
        min(geolocation_city) as representative_city,
        min(geolocation_state) as representative_state,
        count(distinct geolocation_city) as distinct_city_count,
        count(distinct geolocation_state) as distinct_state_count,
        min(source_release_id) as source_release_id,
        min(ingestion_batch_id) as ingestion_batch_id,
        min(dataset_run_id) as dataset_run_id,
        max(ingested_at) as ingested_at
    from source_points
    group by geolocation_zip_prefix
)

select
    cast(geolocation_zip_prefix as varchar) as geolocation_zip_prefix,
    centroid_latitude,
    centroid_longitude,
    cast(source_point_count as number(38, 0)) as source_point_count,
    cast(valid_coordinate_count as number(38, 0)) as valid_coordinate_count,
    cast(invalid_coordinate_count as number(38, 0)) as invalid_coordinate_count,
    cast(representative_city as varchar) as representative_city,
    cast(representative_state as varchar) as representative_state,
    cast(distinct_city_count as number(38, 0)) as distinct_city_count,
    cast(distinct_state_count as number(38, 0)) as distinct_state_count,
    cast(
        case
            when valid_coordinate_count = 0 then 'NO_VALID_COORDINATE'
            when distinct_city_count > 1 or distinct_state_count > 1 then 'AMBIGUOUS_LOCATION'
            when invalid_coordinate_count > 0 then 'PARTIAL_COORDINATE'
            else 'VALID'
        end as varchar
    ) as geolocation_quality_status,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('olist-geolocation-centroid-v1' as varchar) as geolocation_rule_version
from aggregated
