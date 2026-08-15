{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__SEM_SELLER_PERFORMANCE',
    materialized='view',
    tags=['m3_semantic']
) }}

select
    cast(source_release_id as varchar) as data_release_id,
    cast(period_month as date) as period_month,
    cast(seller_key as varchar) as seller_key,
    cast(seller_state as varchar) as seller_state,
    cast(seller_city as varchar) as seller_city,
    cast(order_count as number(38, 0)) as order_count,
    cast(item_count as number(38, 0)) as item_count,
    cast(delivered_order_count as number(38, 0)) as delivered_order_count,
    cast(delivery_eligible_order_count as number(38, 0))
        as delivery_eligible_order_count,
    cast(on_time_order_count as number(38, 0)) as on_time_order_count,
    cast(on_time_delivery_rate as number(38, 18)) as on_time_delivery_rate,
    cast(average_delivery_lead_seconds as number(38, 6))
        as average_delivery_lead_seconds,
    cast(gross_merchandise_value as number(38, 18)) as gross_merchandise_value,
    cast(freight_value as number(38, 18)) as freight_value,
    cast(allocated_review_count as number(38, 18))
        as allocated_review_sample_size,
    cast(allocated_review_score as number(38, 18)) as allocated_review_score,
    cast(average_review_score as number(38, 6)) as average_review_score,
    cast(allocation_policy_version as varchar) as allocation_policy_version,
    cast('NON_ADDITIVE_ACROSS_SELLERS' as varchar) as order_count_usage,
    cast('NOT_AVAILABLE_UNTIL_M4' as varchar) as ai_enrichment_status,
    cast(metric_policy_version as varchar) as metric_policy_version,
    cast('reviewlens-semantic-catalog-v1' as varchar) as semantic_contract_version
from {{ ref('mart_seller_performance') }}
