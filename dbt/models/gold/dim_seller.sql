{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__DIM_SELLER') }}

with unknown_keys as (
    select
        max(iff(entity_type = 'SELLER', unknown_member_key, null)) as seller_key,
        max(iff(entity_type = 'GEOGRAPHY', unknown_member_key, null)) as geography_key,
        min(source_release_id) as source_release_id,
        min(ingestion_batch_id) as ingestion_batch_id
    from {{ reviewlens_silver_candidate_relation('SIL_UNKNOWN_MEMBER_REGISTRY') }}
), source_seller as (
    select
        {{ reviewlens_gold_key(
            'SELLER',
            'seller.seller_id',
            'seller.source_record_hash'
        ) }} as seller_key,
        seller.seller_id,
        coalesce(geography.geography_key, unknown_keys.geography_key) as geography_key,
        seller.seller_zip_prefix,
        seller.seller_city,
        seller.seller_state,
        seller.geolocation_quality_status,
        seller.source_release_id,
        seller.ingestion_batch_id,
        seller.source_record_hash,
        seller.ingested_at as observed_at
    from {{ reviewlens_silver_candidate_relation('SIL_SELLER') }} as seller
    cross join unknown_keys
    left join {{ ref('dim_geography') }} as geography
        on seller.seller_zip_prefix = geography.geolocation_zip_prefix
       and geography.is_current
), unknown_seller as (
    select
        seller_key,
        '__UNKNOWN__' as seller_id,
        geography_key,
        '__UNKNOWN__' as seller_zip_prefix,
        'UNKNOWN' as seller_city,
        'UNKNOWN' as seller_state,
        'UNKNOWN' as geolocation_quality_status,
        source_release_id,
        ingestion_batch_id,
        cast(null as varchar) as source_record_hash,
        cast(null as timestamp_tz(6)) as observed_at
    from unknown_keys
), conformed as (
    select * from source_seller
    union all
    select * from unknown_seller
)

select
    cast(seller_key as varchar) as seller_key,
    cast(seller_id as varchar) as seller_id,
    cast(geography_key as varchar) as geography_key,
    cast(seller_zip_prefix as varchar) as seller_zip_prefix,
    cast(seller_city as varchar) as seller_city,
    cast(seller_state as varchar) as seller_state,
    cast(geolocation_quality_status as varchar) as geolocation_quality_status,
    cast(to_timestamp_ntz('1900-01-01 00:00:00') as timestamp_ntz(6)) as effective_from,
    cast(null as timestamp_ntz(6)) as effective_to,
    cast(true as boolean) as is_current,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(source_record_hash as varchar) as source_record_hash,
    cast(observed_at as timestamp_tz(6)) as observed_at,
    cast('reviewlens-gold-history-v1' as varchar) as history_policy_version,
    cast('reviewlens-dim-seller-v1' as varchar) as model_contract_version
from conformed
