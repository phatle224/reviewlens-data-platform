{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__BRIDGE_REVIEW_ITEM_ATTRIBUTION',
    tags=['m3_review_attribution']
) }}

with unknown_keys as (
    select
        max(iff(entity_type = 'PRODUCT', unknown_member_key, null)) as product_key,
        max(iff(entity_type = 'SELLER', unknown_member_key, null)) as seller_key
    from {{ ref('sil_unknown_member_registry') }}
), review_items as (
    select
        review.review_key,
        review.order_key,
        review.review_id,
        review.order_id,
        review.review_score,
        review.source_release_id,
        review.ingestion_batch_id,
        review.dataset_run_id,
        review.source_record_hash,
        review.ingested_at,
        item.order_item_key,
        item.product_key,
        item.seller_key,
        count(item.order_item_key) over (partition by review.review_key) as item_count_for_review,
        row_number() over (
            partition by review.review_key
            order by item.order_item_id nulls last, item.order_item_key nulls last
        ) as attribution_ordinal
    from {{ ref('fact_review_base') }} as review
    left join {{ ref('fact_order_item') }} as item using (order_id)
), weighted as (
    select
        review_items.*,
        case
            when item_count_for_review = 0 then cast(1 as number(38, 18))
            when attribution_ordinal = item_count_for_review then
                cast(1 as number(38, 18))
                - trunc(
                    cast(1 as number(38, 18)) / item_count_for_review,
                    18
                ) * (item_count_for_review - 1)
            else trunc(
                cast(1 as number(38, 18)) / item_count_for_review,
                18
            )
        end as allocation_weight
    from review_items
)

select
    cast(
        {{ reviewlens_gold_key(
            'REVIEW_ATTRIBUTION',
            "concat_ws(':', review_key, cast(attribution_ordinal as varchar))"
        ) }} as varchar
    ) as attribution_key,
    cast(review_key as varchar) as review_key,
    cast(order_key as varchar) as order_key,
    cast(review_id as varchar) as review_id,
    cast(order_id as varchar) as order_id,
    cast(attribution_ordinal as number(38, 0)) as attribution_ordinal,
    cast(order_item_key as varchar) as order_item_key,
    cast(coalesce(product_key, unknown_keys.product_key) as varchar) as product_key,
    cast(coalesce(seller_key, unknown_keys.seller_key) as varchar) as seller_key,
    cast(item_count_for_review as number(38, 0)) as item_count_for_review,
    cast(
        iff(item_count_for_review = 0, 'UNKNOWN_ITEM_FALLBACK', 'EQUAL_ITEM_WEIGHT')
        as varchar
    ) as allocation_method,
    cast('olist-review-item-equal-weight-v1' as varchar) as allocation_policy_version,
    cast(allocation_weight as number(38, 18)) as allocation_weight,
    cast(allocation_weight as number(38, 18)) as allocated_review_count,
    cast(review_score as number(38, 0)) as review_score,
    cast(review_score * allocation_weight as number(38, 18)) as allocated_review_score,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(source_record_hash as varchar) as source_record_hash,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-bridge-review-item-attribution-v1' as varchar)
        as model_contract_version
from weighted
cross join unknown_keys
