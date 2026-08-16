{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__FACT_ORDER_ITEM') }}

with unknown_keys as (
    select
        max(iff(entity_type = 'PRODUCT', unknown_member_key, null)) as product_key,
        max(iff(entity_type = 'SELLER', unknown_member_key, null)) as seller_key
    from {{ reviewlens_silver_candidate_relation('SIL_UNKNOWN_MEMBER_REGISTRY') }}
), conformed as (
    select
        item.*,
        parent.order_key,
        coalesce(product.product_key, unknown_keys.product_key) as product_key,
        coalesce(seller.seller_key, unknown_keys.seller_key) as seller_key
    from {{ reviewlens_silver_candidate_relation('SIL_ORDER_ITEM') }} as item
    cross join unknown_keys
    inner join {{ ref('fact_order') }} as parent using (order_id)
    left join {{ ref('dim_product') }} as product
        on item.product_id = product.product_id
       and parent.order_purchase_timestamp >= product.effective_from
       and parent.order_purchase_timestamp
            < coalesce(product.effective_to, to_timestamp_ntz('9999-12-31 00:00:00'))
    left join {{ ref('dim_seller') }} as seller
        on item.seller_id = seller.seller_id
       and parent.order_purchase_timestamp >= seller.effective_from
       and parent.order_purchase_timestamp
            < coalesce(seller.effective_to, to_timestamp_ntz('9999-12-31 00:00:00'))
    where item.order_parent_exists
      and item.amount_quality_status = 'VALID'
)

select
    cast(
        {{ reviewlens_gold_key(
            'ORDER_ITEM',
            "concat_ws(':', order_id, cast(order_item_id as varchar))"
        ) }} as varchar
    ) as order_item_key,
    cast(order_key as varchar) as order_key,
    cast(order_id as varchar) as order_id,
    cast(order_item_id as number(38, 0)) as order_item_id,
    cast(product_key as varchar) as product_key,
    cast(seller_key as varchar) as seller_key,
    cast(to_number(to_char(shipping_limit_date, 'YYYYMMDD')) as number(38, 0))
        as shipping_limit_date_key,
    cast(shipping_limit_date as timestamp_ntz(6)) as shipping_limit_date,
    cast(price as number(38, 18)) as price,
    cast(freight_value as number(38, 18)) as freight_value,
    cast(item_total_value as number(38, 18)) as item_total_value,
    cast(1 as number(38, 0)) as item_count,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(source_record_hash as varchar) as source_record_hash,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-fact-order-item-v1' as varchar) as model_contract_version
from conformed
