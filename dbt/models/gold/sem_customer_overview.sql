{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__SEM_CUSTOMER_OVERVIEW',
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
    cast(unknown_customer_order_count as number(38, 0))
        as unknown_customer_order_count,
    cast(customer_count as number(38, 0)) as customer_count,
    cast(repeat_customer_count as number(38, 0)) as repeat_customer_count,
    cast(repeat_customer_rate as number(38, 18)) as repeat_customer_rate,
    cast(gross_merchandise_value as number(38, 18)) as gross_merchandise_value,
    cast(freight_value as number(38, 18)) as freight_value,
    cast(payment_value as number(38, 18)) as payment_value,
    cast(payment_reconciliation_delta as number(38, 18))
        as payment_reconciliation_delta,
    cast(repeat_customer_definition_version as varchar)
        as repeat_customer_definition_version,
    cast('DATASET_GMV_PROXY_NOT_ACCOUNTING_REVENUE' as varchar) as gmv_semantics,
    cast(metric_policy_version as varchar) as metric_policy_version,
    cast('reviewlens-semantic-catalog-v1' as varchar) as semantic_contract_version
from {{ ref('mart_customer_overview') }}
