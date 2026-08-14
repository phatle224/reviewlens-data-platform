{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_SELLER') }}

with ranked_seller as (
    select
        seller_id,
        lpad(trim(seller_zip_code_prefix), 5, '0') as seller_zip_prefix,
        coalesce(nullif(upper(trim(seller_city)), ''), 'UNKNOWN') as seller_city,
        coalesce(nullif(upper(trim(seller_state)), ''), 'UNKNOWN') as seller_state,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        record_hash,
        source_row_number,
        ingested_at,
        {{ reviewlens_revision_rank('seller_id') }} as source_rank
    from {{ source('bronze_olist', 'sellers') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
), joined as (
    select
        source_seller.* exclude source_rank,
        geography.geolocation_zip_prefix is not null as geolocation_zip_exists,
        coalesce(geography.geolocation_quality_status, 'ZIP_NOT_FOUND')
            as geolocation_quality_status
    from ranked_seller as source_seller
    left join {{ ref('sil_geolocation_zip') }} as geography
        on source_seller.seller_zip_prefix = geography.geolocation_zip_prefix
    where source_rank = 1
)

select
    cast(seller_id as varchar) as seller_id,
    cast(seller_zip_prefix as varchar) as seller_zip_prefix,
    cast(seller_city as varchar) as seller_city,
    cast(seller_state as varchar) as seller_state,
    cast(geolocation_zip_exists as boolean) as geolocation_zip_exists,
    cast(geolocation_quality_status as varchar) as geolocation_quality_status,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(record_hash as varchar) as source_record_hash,
    cast(source_row_number as number(38, 0)) as source_row_number,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-sil-seller-v1' as varchar) as model_contract_version
from joined
