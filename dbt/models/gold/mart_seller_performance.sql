{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__MART_SELLER_PERFORMANCE',
    tags=['m3_gold_marts']
) }}

with seller_orders as (
    select
        purchase_date.month_start_date as period_month,
        item.seller_key,
        orders.order_key,
        orders.order_status,
        orders.delivery_interval_valid,
        orders.delivery_lead_seconds,
        orders.delivery_delay_seconds,
        orders.is_on_time_delivery,
        sum(item.item_count) as item_count,
        sum(item.price) as gross_merchandise_value,
        sum(item.freight_value) as freight_value,
        min(item.source_release_id) as source_release_id
    from {{ ref('fact_order_item') }} as item
    inner join {{ ref('fact_order') }} as orders using (order_key)
    inner join {{ ref('dim_date') }} as purchase_date
        on orders.purchase_date_key = purchase_date.date_key
    group by
        purchase_date.month_start_date,
        item.seller_key,
        orders.order_key,
        orders.order_status,
        orders.delivery_interval_valid,
        orders.delivery_lead_seconds,
        orders.delivery_delay_seconds,
        orders.is_on_time_delivery
), item_metrics as (
    select
        period_month,
        seller_key,
        count(distinct order_key) as order_count,
        sum(item_count) as item_count,
        sum(iff(order_status = 'delivered', 1, 0)) as delivered_order_count,
        sum(iff(
            order_status = 'delivered'
            and delivery_interval_valid
            and delivery_lead_seconds is not null
            and delivery_delay_seconds is not null
            and is_on_time_delivery is not null,
            1,
            0
        )) as delivery_eligible_order_count,
        sum(iff(
            order_status = 'delivered'
            and delivery_interval_valid
            and delivery_lead_seconds is not null
            and delivery_delay_seconds is not null
            and is_on_time_delivery is not null
            and is_on_time_delivery,
            1,
            0
        )) as on_time_order_count,
        avg(iff(
            order_status = 'delivered'
            and delivery_interval_valid
            and delivery_lead_seconds is not null
            and delivery_delay_seconds is not null
            and is_on_time_delivery is not null,
            delivery_lead_seconds,
            null
        )) as average_delivery_lead_seconds,
        sum(gross_merchandise_value) as gross_merchandise_value,
        sum(freight_value) as freight_value,
        min(source_release_id) as source_release_id
    from seller_orders
    group by period_month, seller_key
), review_metrics as (
    select
        purchase_date.month_start_date as period_month,
        attribution.seller_key,
        sum(attribution.allocated_review_count) as allocated_review_count,
        sum(attribution.allocated_review_score) as allocated_review_score,
        min(attribution.allocation_policy_version) as allocation_policy_version,
        min(attribution.source_release_id) as source_release_id
    from {{ ref('bridge_review_item_attribution') }} as attribution
    inner join {{ ref('fact_order') }} as orders using (order_key)
    inner join {{ ref('dim_date') }} as purchase_date
        on orders.purchase_date_key = purchase_date.date_key
    group by purchase_date.month_start_date, attribution.seller_key
), combined as (
    select
        coalesce(items.period_month, reviews.period_month) as period_month,
        coalesce(items.seller_key, reviews.seller_key) as seller_key,
        coalesce(items.order_count, 0) as order_count,
        coalesce(items.item_count, 0) as item_count,
        coalesce(items.delivered_order_count, 0) as delivered_order_count,
        coalesce(items.delivery_eligible_order_count, 0) as delivery_eligible_order_count,
        coalesce(items.on_time_order_count, 0) as on_time_order_count,
        items.average_delivery_lead_seconds,
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
       and items.seller_key = reviews.seller_key
)

select
    cast({{ reviewlens_gold_key(
        'MART_SELLER_PERFORMANCE',
        "concat_ws(':', to_char(combined.period_month, 'YYYY-MM-DD'), combined.seller_key)"
    ) }} as varchar) as seller_performance_mart_key,
    cast(combined.period_month as date) as period_month,
    cast(combined.seller_key as varchar) as seller_key,
    cast(seller.geography_key as varchar) as geography_key,
    cast(seller.seller_state as varchar) as seller_state,
    cast(seller.seller_city as varchar) as seller_city,
    cast(combined.order_count as number(38, 0)) as order_count,
    cast(combined.item_count as number(38, 0)) as item_count,
    cast(combined.delivered_order_count as number(38, 0)) as delivered_order_count,
    cast(combined.delivery_eligible_order_count as number(38, 0))
        as delivery_eligible_order_count,
    cast(combined.on_time_order_count as number(38, 0)) as on_time_order_count,
    cast(
        combined.on_time_order_count / nullif(combined.delivery_eligible_order_count, 0)
        as number(38, 18)
    ) as on_time_delivery_rate,
    cast(combined.average_delivery_lead_seconds as number(38, 6))
        as average_delivery_lead_seconds,
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
    cast('reviewlens-mart-seller-performance-v1' as varchar) as model_contract_version
from combined
inner join {{ ref('dim_seller') }} as seller using (seller_key)
