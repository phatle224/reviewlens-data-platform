{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_PRODUCT') }}

with ranked_product as (
    select
        product_id,
        lower(trim(product_category_name)) as product_category_name,
        product_name_lenght,
        product_description_lenght,
        product_photos_qty,
        product_weight_g,
        product_length_cm,
        product_height_cm,
        product_width_cm,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        record_hash,
        source_row_number,
        ingested_at,
        {{ reviewlens_revision_rank('product_id') }} as source_rank
    from {{ source('bronze_olist', 'products') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
), joined as (
    select
        source_product.* exclude source_rank,
        coalesce(translation.product_category_name_english, 'UNKNOWN')
            as product_category_name_english,
        translation.product_category_name is not null as category_translation_exists
    from ranked_product as source_product
    left join {{ ref('sil_category_translation') }} as translation
        using (product_category_name)
    where source_rank = 1
)

select
    cast(product_id as varchar) as product_id,
    cast(coalesce(product_category_name, 'unknown') as varchar) as product_category_name,
    cast(product_category_name_english as varchar) as product_category_name_english,
    cast(category_translation_exists as boolean) as category_translation_exists,
    cast(product_name_lenght as number(38, 0)) as product_name_length,
    cast(product_description_lenght as number(38, 0)) as product_description_length,
    cast(product_photos_qty as number(38, 0)) as product_photos_qty,
    cast(product_weight_g as number(38, 18)) as product_weight_g,
    cast(product_length_cm as number(38, 18)) as product_length_cm,
    cast(product_height_cm as number(38, 18)) as product_height_cm,
    cast(product_width_cm as number(38, 18)) as product_width_cm,
    cast(
        case
            when product_category_name is null then 'UNKNOWN_CATEGORY'
            when not category_translation_exists then 'UNTRANSLATED_CATEGORY'
            else 'VALID'
        end as varchar
    ) as product_quality_status,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(record_hash as varchar) as source_record_hash,
    cast(source_row_number as number(38, 0)) as source_row_number,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-sil-product-v1' as varchar) as model_contract_version
from joined
