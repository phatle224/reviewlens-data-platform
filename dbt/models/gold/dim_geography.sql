{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__DIM_GEOGRAPHY') }}

with source_geography as (
    select
        {{ reviewlens_gold_key(
            'GEOGRAPHY',
            'geolocation_zip_prefix',
            'source_release_id'
        ) }} as geography_key,
        geolocation_zip_prefix,
        representative_city as city,
        representative_state as state,
        centroid_latitude,
        centroid_longitude,
        geolocation_quality_status,
        source_point_count,
        valid_coordinate_count,
        invalid_coordinate_count,
        source_release_id,
        ingestion_batch_id,
        ingested_at as observed_at
    from {{ reviewlens_silver_candidate_relation('SIL_GEOLOCATION_ZIP') }}
), unknown_geography as (
    select
        unknown_member_key as geography_key,
        '__UNKNOWN__' as geolocation_zip_prefix,
        display_label as city,
        display_label as state,
        cast(null as number(38, 18)) as centroid_latitude,
        cast(null as number(38, 18)) as centroid_longitude,
        'UNKNOWN' as geolocation_quality_status,
        0 as source_point_count,
        0 as valid_coordinate_count,
        0 as invalid_coordinate_count,
        source_release_id,
        ingestion_batch_id,
        cast(null as timestamp_tz(6)) as observed_at
    from {{ reviewlens_silver_candidate_relation('SIL_UNKNOWN_MEMBER_REGISTRY') }}
    where entity_type = 'GEOGRAPHY'
), conformed as (
    select * from source_geography
    union all
    select * from unknown_geography
)

select
    cast(geography_key as varchar) as geography_key,
    cast(geolocation_zip_prefix as varchar) as geolocation_zip_prefix,
    cast(city as varchar) as city,
    cast(state as varchar) as state,
    cast(centroid_latitude as number(38, 18)) as centroid_latitude,
    cast(centroid_longitude as number(38, 18)) as centroid_longitude,
    cast(geolocation_quality_status as varchar) as geolocation_quality_status,
    cast(source_point_count as number(38, 0)) as source_point_count,
    cast(valid_coordinate_count as number(38, 0)) as valid_coordinate_count,
    cast(invalid_coordinate_count as number(38, 0)) as invalid_coordinate_count,
    cast(to_timestamp_ntz('1900-01-01 00:00:00') as timestamp_ntz(6)) as effective_from,
    cast(null as timestamp_ntz(6)) as effective_to,
    cast(true as boolean) as is_current,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(observed_at as timestamp_tz(6)) as observed_at,
    cast('reviewlens-gold-history-v1' as varchar) as history_policy_version,
    cast('reviewlens-dim-geography-v1' as varchar) as model_contract_version
from conformed
