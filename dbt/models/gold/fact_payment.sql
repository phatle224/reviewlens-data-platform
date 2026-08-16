{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__FACT_PAYMENT') }}

with conformed as (
    select payment.*, parent.order_key
    from {{ reviewlens_silver_candidate_relation('SIL_ORDER_PAYMENT') }} as payment
    inner join {{ ref('fact_order') }} as parent using (order_id)
    where payment.order_parent_exists
      and payment.amount_quality_status = 'VALID'
)

select
    cast(
        {{ reviewlens_gold_key(
            'PAYMENT',
            "concat_ws(':', order_id, cast(payment_sequential as varchar))"
        ) }} as varchar
    ) as payment_key,
    cast(order_key as varchar) as order_key,
    cast(order_id as varchar) as order_id,
    cast(payment_sequential as number(38, 0)) as payment_sequential,
    cast(payment_type as varchar) as payment_type,
    cast(payment_installments as number(38, 0)) as payment_installments,
    cast(payment_value as number(38, 18)) as payment_value,
    cast(1 as number(38, 0)) as payment_count,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(source_record_hash as varchar) as source_record_hash,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-fact-payment-v1' as varchar) as model_contract_version
from conformed
