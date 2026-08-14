{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_ORDER') }}

with ranked_order as (
    select
        order_id,
        customer_id,
        lower(trim(order_status)) as order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        record_hash,
        source_row_number,
        ingested_at,
        row_number() over (
            partition by order_id
            order by ingested_at desc, source_row_number desc, record_hash desc
        ) as source_rank
    from {{ source('bronze_olist', 'orders') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
), customer_keys as (
    select distinct customer_id
    from {{ source('bronze_olist', 'customers') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
), item_counts as (
    select order_id, count(*) as valid_item_count
    from {{ source('bronze_olist', 'order_items') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
    group by order_id
), joined as (
    select
        source_order.* exclude source_rank,
        customer_keys.customer_id is not null as customer_exists,
        coalesce(item_counts.valid_item_count, 0) as valid_item_count,
        order_delivered_customer_date is not null
            and order_delivered_customer_date >= order_purchase_timestamp
            as delivery_interval_valid
    from ranked_order as source_order
    left join customer_keys using (customer_id)
    left join item_counts using (order_id)
    where source_rank = 1
)

select
    cast(order_id as varchar) as order_id,
    cast(customer_id as varchar) as customer_id,
    cast(order_status as varchar) as order_status,
    cast(order_purchase_timestamp as timestamp_ntz(6)) as order_purchase_timestamp,
    cast(order_approved_at as timestamp_ntz(6)) as order_approved_at,
    cast(order_delivered_carrier_date as timestamp_ntz(6)) as order_delivered_carrier_date,
    cast(order_delivered_customer_date as timestamp_ntz(6)) as order_delivered_customer_date,
    cast(order_estimated_delivery_date as timestamp_ntz(6)) as order_estimated_delivery_date,
    cast(customer_exists as boolean) as customer_exists,
    cast(valid_item_count as number(38, 0)) as valid_item_count,
    cast(delivery_interval_valid as boolean) as delivery_interval_valid,
    cast(
        case
            when order_status = 'delivered' and customer_exists and valid_item_count > 0
                then 'IN_SCOPE'
            when order_status = 'delivered' then 'QUARANTINED'
            when order_status in ('canceled', 'unavailable') then 'OUT_OF_SCOPE_DELIVERY'
            when order_status in ('approved', 'created', 'invoiced', 'processing', 'shipped')
                then 'OUT_OF_SCOPE_DELIVERY'
            else 'UNKNOWN'
        end as varchar
    ) as analysis_scope_status,
    cast(
        case
            when order_status = 'delivered' and not customer_exists then 'MISSING_CUSTOMER'
            when order_status = 'delivered' and valid_item_count = 0 then 'MISSING_ORDER_ITEM'
            when order_status = 'delivered' then 'ELIGIBLE_DELIVERED'
            when order_status in ('canceled', 'unavailable') then 'TERMINAL_NON_DELIVERY'
            when order_status in ('approved', 'created', 'invoiced', 'processing', 'shipped')
                then 'NOT_DELIVERED'
            else 'UNRECOGNIZED_STATUS'
        end as varchar
    ) as analysis_scope_reason,
    cast('olist_order_scope_v1' as varchar) as analysis_scope_version,
    cast('olist-brazil-local-civil-v1' as varchar) as time_policy_version,
    cast(
        iff(
            delivery_interval_valid,
            datediff('second', order_purchase_timestamp, order_delivered_customer_date),
            null
        ) as number(38, 0)
    ) as delivery_lead_seconds,
    cast(
        iff(
            delivery_interval_valid,
            datediff('second', order_estimated_delivery_date, order_delivered_customer_date),
            null
        ) as number(38, 0)
    ) as delivery_delay_seconds,
    cast(
        iff(
            delivery_interval_valid,
            order_delivered_customer_date <= order_estimated_delivery_date,
            null
        ) as boolean
    ) as is_on_time_delivery,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(record_hash as varchar) as source_record_hash,
    cast(source_row_number as number(38, 0)) as source_row_number,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-sil-order-v1' as varchar) as model_contract_version
from joined
