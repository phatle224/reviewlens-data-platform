{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_ORDER_ITEM') }}

with ranked_item as (
    select
        order_id,
        order_item_id,
        product_id,
        seller_id,
        shipping_limit_date,
        price,
        freight_value,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        record_hash,
        source_row_number,
        ingested_at,
        {{ reviewlens_revision_rank('order_id, order_item_id') }} as source_rank
    from {{ source('bronze_olist', 'order_items') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
), joined as (
    select
        source_item.* exclude source_rank,
        parent_order.order_id is not null as order_parent_exists
    from ranked_item as source_item
    left join {{ ref('sil_order') }} as parent_order using (order_id)
    where source_rank = 1
)

select
    cast(order_id as varchar) as order_id,
    cast(order_item_id as number(38, 0)) as order_item_id,
    cast(product_id as varchar) as product_id,
    cast(seller_id as varchar) as seller_id,
    cast(shipping_limit_date as timestamp_ntz(6)) as shipping_limit_date,
    cast(price as number(38, 18)) as price,
    cast(freight_value as number(38, 18)) as freight_value,
    cast(price + freight_value as number(38, 18)) as item_total_value,
    cast(order_parent_exists as boolean) as order_parent_exists,
    cast(
        case
            when not order_parent_exists then 'ORPHAN_ORDER'
            when price <= 0 then 'INVALID_PRICE'
            when freight_value < 0 then 'INVALID_FREIGHT'
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
    cast('reviewlens-sil-order-item-v1' as varchar) as model_contract_version
from joined
