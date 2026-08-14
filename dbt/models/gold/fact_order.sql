{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__FACT_ORDER') }}

with unknown_customer as (
    select unknown_member_key as customer_key
    from {{ ref('sil_unknown_member_registry') }}
    where entity_type = 'CUSTOMER'
), conformed as (
    select
        source_order.*,
        coalesce(customer.customer_key, unknown_customer.customer_key) as customer_key
    from {{ ref('sil_order') }} as source_order
    cross join unknown_customer
    left join {{ ref('dim_customer') }} as customer
        on source_order.customer_id = customer.customer_id
       and source_order.order_purchase_timestamp >= customer.effective_from
       and source_order.order_purchase_timestamp
            < coalesce(customer.effective_to, to_timestamp_ntz('9999-12-31 00:00:00'))
    where source_order.analysis_scope_status != 'QUARANTINED'
)

select
    cast({{ reviewlens_gold_key('ORDER', 'order_id') }} as varchar) as order_key,
    cast(order_id as varchar) as order_id,
    cast(customer_key as varchar) as customer_key,
    cast(to_number(to_char(order_purchase_timestamp, 'YYYYMMDD')) as number(38, 0))
        as purchase_date_key,
    cast(
        iff(
            order_delivered_customer_date is null,
            null,
            to_number(to_char(order_delivered_customer_date, 'YYYYMMDD'))
        ) as number(38, 0)
    ) as delivered_date_key,
    cast(to_number(to_char(order_estimated_delivery_date, 'YYYYMMDD')) as number(38, 0))
        as estimated_delivery_date_key,
    cast(order_status as varchar) as order_status,
    cast(analysis_scope_status as varchar) as analysis_scope_status,
    cast(analysis_scope_reason as varchar) as analysis_scope_reason,
    cast(order_purchase_timestamp as timestamp_ntz(6)) as order_purchase_timestamp,
    cast(order_delivered_customer_date as timestamp_ntz(6)) as order_delivered_customer_date,
    cast(order_estimated_delivery_date as timestamp_ntz(6)) as order_estimated_delivery_date,
    cast(delivery_interval_valid as boolean) as delivery_interval_valid,
    cast(delivery_lead_seconds as number(38, 0)) as delivery_lead_seconds,
    cast(delivery_delay_seconds as number(38, 0)) as delivery_delay_seconds,
    cast(is_on_time_delivery as boolean) as is_on_time_delivery,
    cast(1 as number(38, 0)) as order_count,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(source_record_hash as varchar) as source_record_hash,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-fact-order-v1' as varchar) as model_contract_version
from conformed
