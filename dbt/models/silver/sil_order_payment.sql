{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_ORDER_PAYMENT') }}

with ranked_payment as (
    select
        order_id,
        payment_sequential,
        lower(trim(payment_type)) as payment_type,
        payment_installments,
        payment_value,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        record_hash,
        source_row_number,
        ingested_at,
        {{ reviewlens_revision_rank('order_id, payment_sequential') }} as source_rank
    from {{ source('bronze_olist', 'order_payments') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
), joined as (
    select
        source_payment.* exclude source_rank,
        parent_order.order_id is not null as order_parent_exists
    from ranked_payment as source_payment
    left join {{ ref('sil_order') }} as parent_order using (order_id)
    where source_rank = 1
)

select
    cast(order_id as varchar) as order_id,
    cast(payment_sequential as number(38, 0)) as payment_sequential,
    cast(payment_type as varchar) as payment_type,
    cast(payment_installments as number(38, 0)) as payment_installments,
    cast(payment_value as number(38, 18)) as payment_value,
    cast(order_parent_exists as boolean) as order_parent_exists,
    cast(
        case
            when not order_parent_exists then 'ORPHAN_ORDER'
            when payment_value < 0 then 'INVALID_PAYMENT_VALUE'
            when payment_installments < 0 then 'INVALID_INSTALLMENTS'
            else 'VALID'
        end as varchar
    ) as amount_quality_status,
    cast('olist-amount-quality-v1' as varchar) as amount_quality_version,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(record_hash as varchar) as source_record_hash,
    cast(source_row_number as number(38, 0)) as source_row_number,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-sil-order-payment-v1' as varchar) as model_contract_version
from joined
