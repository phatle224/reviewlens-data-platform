{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_CUSTOMER') }}

with ranked_customer as (
    select
        customer_id,
        customer_unique_id,
        customer_zip_code_prefix,
        customer_city,
        customer_state,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        record_hash,
        source_row_number,
        ingested_at,
        row_number() over (
            partition by customer_id
            order by ingested_at desc, source_row_number desc, record_hash desc
        ) as source_rank
    from {{ source('bronze_olist', 'customers') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
)

select
    cast(customer_id as varchar) as customer_id,
    sha2(concat('reviewlens-repeat-customer-v1', chr(0), trim(customer_unique_id)), 256)
        as repeat_customer_key,
    cast(lpad(trim(customer_zip_code_prefix), 5, '0') as varchar) as customer_zip_prefix,
    cast(coalesce(nullif(upper(trim(customer_city)), ''), 'UNKNOWN') as varchar)
        as customer_city,
    cast(coalesce(nullif(upper(trim(customer_state)), ''), 'UNKNOWN') as varchar)
        as customer_state,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(record_hash as varchar) as source_record_hash,
    cast(source_row_number as number(38, 0)) as source_row_number,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-sil-customer-v1' as varchar) as model_contract_version
from ranked_customer
where source_rank = 1
