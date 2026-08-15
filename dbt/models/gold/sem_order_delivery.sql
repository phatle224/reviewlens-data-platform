{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__SEM_ORDER_DELIVERY',
    materialized='view',
    tags=['m3_semantic']
) }}

select
    cast(source_release_id as varchar) as data_release_id,
    cast(period_month as date) as period_month,
    cast(geography_key as varchar) as geography_key,
    cast(geography_state as varchar) as geography_state,
    cast(geography_city as varchar) as geography_city,
    cast(order_count as number(38, 0)) as order_count,
    cast(delivered_order_count as number(38, 0)) as delivered_order_count,
    cast(cancelled_order_count as number(38, 0)) as cancelled_order_count,
    cast(delivery_eligible_order_count as number(38, 0))
        as delivery_eligible_order_count,
    cast(on_time_order_count as number(38, 0)) as on_time_order_count,
    cast(on_time_delivery_rate as number(38, 18)) as on_time_delivery_rate,
    cast(average_delivery_lead_seconds as number(38, 6))
        as average_delivery_lead_seconds,
    cast(average_delivery_delay_seconds as number(38, 6))
        as average_delivery_delay_seconds,
    cast(gross_merchandise_value as number(38, 18)) as gross_merchandise_value,
    cast(freight_value as number(38, 18)) as freight_value,
    cast(payment_value as number(38, 18)) as payment_value,
    cast(payment_reconciliation_delta as number(38, 18))
        as payment_reconciliation_delta,
    cast('DATASET_GMV_PROXY_NOT_ACCOUNTING_REVENUE' as varchar) as gmv_semantics,
    cast(metric_policy_version as varchar) as metric_policy_version,
    cast('reviewlens-semantic-catalog-v1' as varchar) as semantic_contract_version
from {{ ref('mart_order_delivery') }}
