{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__MART_CUSTOMER_OVERVIEW',
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
), lifetime_customer_orders as (
    select
        customer.repeat_customer_key,
        count(distinct orders.order_key) as lifetime_order_count
    from {{ ref('fact_order') }} as orders
    inner join {{ ref('dim_customer') }} as customer using (customer_key)
    where customer.customer_id != '__UNKNOWN__'
    group by customer.repeat_customer_key
), order_metrics as (
    select
        purchase_date.month_start_date as period_month,
        customer.geography_key,
        geography.state as geography_state,
        geography.city as geography_city,
        orders.order_key,
        orders.order_status,
        customer.customer_id,
        customer.repeat_customer_key,
        coalesce(lifetime.lifetime_order_count, 0) as lifetime_order_count,
        coalesce(items.gross_merchandise_value, 0) as gross_merchandise_value,
        coalesce(items.freight_value, 0) as freight_value,
        coalesce(payments.payment_value, 0) as payment_value,
        orders.source_release_id
    from {{ ref('fact_order') }} as orders
    inner join {{ ref('dim_date') }} as purchase_date
        on orders.purchase_date_key = purchase_date.date_key
    inner join {{ ref('dim_customer') }} as customer using (customer_key)
    inner join {{ ref('dim_geography') }} as geography using (geography_key)
    left join lifetime_customer_orders as lifetime using (repeat_customer_key)
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
        sum(iff(customer_id = '__UNKNOWN__', 1, 0)) as unknown_customer_order_count,
        count(distinct iff(
            customer_id != '__UNKNOWN__',
            repeat_customer_key,
            null
        )) as customer_count,
        count(distinct iff(
            customer_id != '__UNKNOWN__' and lifetime_order_count > 1,
            repeat_customer_key,
            null
        )) as repeat_customer_count,
        sum(gross_merchandise_value) as gross_merchandise_value,
        sum(freight_value) as freight_value,
        sum(payment_value) as payment_value,
        min(source_release_id) as source_release_id
    from order_metrics
    group by period_month, geography_key, geography_state, geography_city
)

select
    cast({{ reviewlens_gold_key(
        'MART_CUSTOMER_OVERVIEW',
        "concat_ws(':', to_char(period_month, 'YYYY-MM-DD'), geography_key)"
    ) }} as varchar) as customer_overview_mart_key,
    cast(period_month as date) as period_month,
    cast(geography_key as varchar) as geography_key,
    cast(geography_state as varchar) as geography_state,
    cast(geography_city as varchar) as geography_city,
    cast(order_count as number(38, 0)) as order_count,
    cast(delivered_order_count as number(38, 0)) as delivered_order_count,
    cast(cancelled_order_count as number(38, 0)) as cancelled_order_count,
    cast(unknown_customer_order_count as number(38, 0))
        as unknown_customer_order_count,
    cast(customer_count as number(38, 0)) as customer_count,
    cast(repeat_customer_count as number(38, 0)) as repeat_customer_count,
    cast(
        repeat_customer_count / nullif(customer_count, 0)
        as number(38, 18)
    ) as repeat_customer_rate,
    cast(gross_merchandise_value as number(38, 18)) as gross_merchandise_value,
    cast(freight_value as number(38, 18)) as freight_value,
    cast(payment_value as number(38, 18)) as payment_value,
    cast(
        payment_value - gross_merchandise_value - freight_value
        as number(38, 18)
    ) as payment_reconciliation_delta,
    cast('olist-repeat-customer-lifetime-v1' as varchar)
        as repeat_customer_definition_version,
    cast('olist-metric-dictionary-v1' as varchar) as metric_policy_version,
    cast(source_release_id as varchar) as source_release_id,
    cast('reviewlens-mart-customer-overview-v1' as varchar) as model_contract_version
from aggregated
