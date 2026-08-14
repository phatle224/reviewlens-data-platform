{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_CATEGORY_TRANSLATION') }}

with ranked_translation as (
    select
        lower(trim(product_category_name)) as product_category_name,
        upper(trim(product_category_name_english)) as product_category_name_english,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        record_hash,
        source_row_number,
        ingested_at,
        {{ reviewlens_revision_rank('lower(trim(product_category_name))') }} as source_rank
    from {{ source('bronze_olist', 'category_translation') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
)

select
    cast(product_category_name as varchar) as product_category_name,
    cast(
        coalesce(nullif(product_category_name_english, ''), 'UNKNOWN') as varchar
    ) as product_category_name_english,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(record_hash as varchar) as source_record_hash,
    cast(source_row_number as number(38, 0)) as source_row_number,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-sil-category-translation-v1' as varchar) as model_contract_version
from ranked_translation
where source_rank = 1
