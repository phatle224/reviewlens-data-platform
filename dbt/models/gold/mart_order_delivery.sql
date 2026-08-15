{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__MART_ORDER_DELIVERY',
    tags=['m3_gold_marts']
) }}

with order_item_totals as (
    select
        order_key,
        sum(price) as gross_merchandise_value,
        sum(freight_value) as freight_value
    from {{ ref('fact_order_item') }}
    group by order_key
), payment_totals as (
    select order_key, sum(payment_value) as payment_value
    from {{ ref('fact_payment') }}
    group by order_key
), order_metrics as (
    select
        purchase_date.month_start_date as period_month,
        customer.geography_key,
        geography.state as geography_state,
        geography.city as geography_city,
        orders.order_key,
        orders.order_status,
        orders.delivery_interval_valid,
        orders.delivery_lead_seconds,
        orders.delivery_delay_seconds,
        orders.is_on_time_delivery,
        coalesce(items.gross_merchandise_value, 0) as gross_merchandise_value,
        coalesce(items.freight_value, 0) as freight_value,
        coalesce(payments.payment_value, 0) as payment_value,
        orders.source_release_id
    from {{ ref('fact_order') }} as orders
    inner join {{ ref('dim_date') }} as purchase_date
        on orders.purchase_date_key = purchase_date.date_key
    inner join {{ ref('dim_customer') }} as customer using (customer_key)
    inner join {{ ref('dim_geography') }} as geography using (geography_key)
    left join order_item_totals as items using (order_key)
    left join payment_totals as payments using (order_key)
), aggregated as (
    select
        period_month,
        geography_key,
        geography_state,
        geography_city,
        count(*) as order_count,
        sum(iff(order_status = 'delivered', 1, 0)) as delivered_order_count,
        sum(iff(order_status = 'canceled', 1, 0)) as cancelled_order_count,
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
        avg(iff(
            order_status = 'delivered'
            and delivery_interval_valid
            and delivery_lead_seconds is not null
            and delivery_delay_seconds is not null
            and is_on_time_delivery is not null,
            delivery_delay_seconds,
            null
        )) as average_delivery_delay_seconds,
        sum(gross_merchandise_value) as gross_merchandise_value,
        sum(freight_value) as freight_value,
        sum(payment_value) as payment_value,
        min(source_release_id) as source_release_id
    from order_metrics
    group by period_month, geography_key, geography_state, geography_city
)

select
    cast({{ reviewlens_gold_key(
        'MART_ORDER_DELIVERY',
        "concat_ws(':', to_char(period_month, 'YYYY-MM-DD'), geography_key)"
    ) }} as varchar) as delivery_mart_key,
    cast(period_month as date) as period_month,
    cast(geography_key as varchar) as geography_key,
    cast(geography_state as varchar) as geography_state,
    cast(geography_city as varchar) as geography_city,
    cast(order_count as number(38, 0)) as order_count,
    cast(delivered_order_count as number(38, 0)) as delivered_order_count,
    cast(cancelled_order_count as number(38, 0)) as cancelled_order_count,
    cast(delivery_eligible_order_count as number(38, 0)) as delivery_eligible_order_count,
    cast(on_time_order_count as number(38, 0)) as on_time_order_count,
    cast(
        on_time_order_count / nullif(delivery_eligible_order_count, 0)
        as number(38, 18)
    ) as on_time_delivery_rate,
    cast(average_delivery_lead_seconds as number(38, 6))
        as average_delivery_lead_seconds,
    cast(average_delivery_delay_seconds as number(38, 6))
        as average_delivery_delay_seconds,
    cast(gross_merchandise_value as number(38, 18)) as gross_merchandise_value,
    cast(freight_value as number(38, 18)) as freight_value,
    cast(payment_value as number(38, 18)) as payment_value,
    cast(
        payment_value - gross_merchandise_value - freight_value
        as number(38, 18)
    ) as payment_reconciliation_delta,
    cast('olist-metric-dictionary-v1' as varchar) as metric_policy_version,
    cast(source_release_id as varchar) as source_release_id,
    cast('reviewlens-mart-order-delivery-v1' as varchar) as model_contract_version
from aggregated
