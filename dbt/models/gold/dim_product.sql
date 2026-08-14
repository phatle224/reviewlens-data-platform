{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__DIM_PRODUCT') }}

with source_product as (
    select
        {{ reviewlens_gold_key('PRODUCT', 'product_id', 'source_record_hash') }} as product_key,
        product_id,
        product_category_name,
        product_category_name_english,
        product_name_length,
        product_description_length,
        product_photos_qty,
        product_weight_g,
        product_length_cm,
        product_height_cm,
        product_width_cm,
        product_quality_status,
        source_release_id,
        ingestion_batch_id,
        source_record_hash,
        ingested_at as observed_at
    from {{ ref('sil_product') }}
), unknown_product as (
    select
        unknown_member_key as product_key,
        '__UNKNOWN__' as product_id,
        'unknown' as product_category_name,
        display_label as product_category_name_english,
        cast(null as number(38, 0)) as product_name_length,
        cast(null as number(38, 0)) as product_description_length,
        cast(null as number(38, 0)) as product_photos_qty,
        cast(null as number(38, 18)) as product_weight_g,
        cast(null as number(38, 18)) as product_length_cm,
        cast(null as number(38, 18)) as product_height_cm,
        cast(null as number(38, 18)) as product_width_cm,
        'UNKNOWN' as product_quality_status,
        source_release_id,
        ingestion_batch_id,
        cast(null as varchar) as source_record_hash,
        cast(null as timestamp_tz(6)) as observed_at
    from {{ ref('sil_unknown_member_registry') }}
    where entity_type = 'PRODUCT'
), conformed as (
    select * from source_product
    union all
    select * from unknown_product
)

select
    cast(product_key as varchar) as product_key,
    cast(product_id as varchar) as product_id,
    cast(product_category_name as varchar) as product_category_name,
    cast(product_category_name_english as varchar) as product_category_name_english,
    cast(product_name_length as number(38, 0)) as product_name_length,
    cast(product_description_length as number(38, 0)) as product_description_length,
    cast(product_photos_qty as number(38, 0)) as product_photos_qty,
    cast(product_weight_g as number(38, 18)) as product_weight_g,
    cast(product_length_cm as number(38, 18)) as product_length_cm,
    cast(product_height_cm as number(38, 18)) as product_height_cm,
    cast(product_width_cm as number(38, 18)) as product_width_cm,
    cast(product_quality_status as varchar) as product_quality_status,
    cast(to_timestamp_ntz('1900-01-01 00:00:00') as timestamp_ntz(6)) as effective_from,
    cast(null as timestamp_ntz(6)) as effective_to,
    cast(true as boolean) as is_current,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(source_record_hash as varchar) as source_record_hash,
    cast(observed_at as timestamp_tz(6)) as observed_at,
    cast('reviewlens-gold-history-v1' as varchar) as history_policy_version,
    cast('reviewlens-dim-product-v1' as varchar) as model_contract_version
from conformed
