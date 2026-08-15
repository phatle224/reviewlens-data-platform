{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__MART_PRODUCT_REVIEW',
    tags=['m3_gold_marts']
) }}

with item_metrics as (
    select
        purchase_date.month_start_date as period_month,
        item.product_key,
        count(distinct item.order_key) as order_count,
        sum(item.item_count) as item_count,
        sum(item.price) as gross_merchandise_value,
        sum(item.freight_value) as freight_value,
        min(item.source_release_id) as source_release_id
    from {{ ref('fact_order_item') }} as item
    inner join {{ ref('fact_order') }} as orders using (order_key)
    inner join {{ ref('dim_date') }} as purchase_date
        on orders.purchase_date_key = purchase_date.date_key
    group by purchase_date.month_start_date, item.product_key
), review_metrics as (
    select
        purchase_date.month_start_date as period_month,
        attribution.product_key,
        sum(attribution.allocated_review_count) as allocated_review_count,
        sum(attribution.allocated_review_score) as allocated_review_score,
        min(attribution.allocation_policy_version) as allocation_policy_version,
        min(attribution.source_release_id) as source_release_id
    from {{ ref('bridge_review_item_attribution') }} as attribution
    inner join {{ ref('fact_order') }} as orders using (order_key)
    inner join {{ ref('dim_date') }} as purchase_date
        on orders.purchase_date_key = purchase_date.date_key
    group by purchase_date.month_start_date, attribution.product_key
), combined as (
    select
        coalesce(items.period_month, reviews.period_month) as period_month,
        coalesce(items.product_key, reviews.product_key) as product_key,
        coalesce(items.order_count, 0) as order_count,
        coalesce(items.item_count, 0) as item_count,
        coalesce(items.gross_merchandise_value, 0) as gross_merchandise_value,
        coalesce(items.freight_value, 0) as freight_value,
        coalesce(reviews.allocated_review_count, 0) as allocated_review_count,
        coalesce(reviews.allocated_review_score, 0) as allocated_review_score,
        coalesce(
            reviews.allocation_policy_version,
            'olist-review-item-equal-weight-v1'
        ) as allocation_policy_version,
        coalesce(items.source_release_id, reviews.source_release_id) as source_release_id
    from item_metrics as items
    full outer join review_metrics as reviews
        on items.period_month = reviews.period_month
       and items.product_key = reviews.product_key
)

select
    cast({{ reviewlens_gold_key(
        'MART_PRODUCT_REVIEW',
        "concat_ws(':', to_char(combined.period_month, 'YYYY-MM-DD'), combined.product_key)"
    ) }} as varchar) as product_review_mart_key,
    cast(combined.period_month as date) as period_month,
    cast(combined.product_key as varchar) as product_key,
    cast(product.product_category_name as varchar) as product_category_name,
    cast(product.product_category_name_english as varchar)
        as product_category_name_english,
    cast(combined.order_count as number(38, 0)) as order_count,
    cast(combined.item_count as number(38, 0)) as item_count,
    cast(combined.gross_merchandise_value as number(38, 18))
        as gross_merchandise_value,
    cast(combined.freight_value as number(38, 18)) as freight_value,
    cast(combined.allocated_review_count as number(38, 18))
        as allocated_review_count,
    cast(combined.allocated_review_score as number(38, 18))
        as allocated_review_score,
    cast(
        combined.allocated_review_score / nullif(combined.allocated_review_count, 0)
        as number(38, 6)
    ) as average_review_score,
    cast(combined.allocation_policy_version as varchar) as allocation_policy_version,
    cast('olist-metric-dictionary-v1' as varchar) as metric_policy_version,
    cast(combined.source_release_id as varchar) as source_release_id,
    cast('reviewlens-mart-product-review-v1' as varchar) as model_contract_version
from combined
inner join {{ ref('dim_product') }} as product using (product_key)
