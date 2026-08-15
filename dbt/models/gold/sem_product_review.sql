{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(
    alias=candidate_namespace ~ '__SEM_PRODUCT_REVIEW',
    materialized='view',
    tags=['m3_semantic']
) }}

select
    cast(source_release_id as varchar) as data_release_id,
    cast(period_month as date) as period_month,
    cast(product_key as varchar) as product_key,
    cast(product_category_name as varchar) as product_category_name,
    cast(product_category_name_english as varchar)
        as product_category_name_english,
    cast(order_count as number(38, 0)) as order_count,
    cast(item_count as number(38, 0)) as item_count,
    cast(gross_merchandise_value as number(38, 18)) as gross_merchandise_value,
    cast(freight_value as number(38, 18)) as freight_value,
    cast(allocated_review_count as number(38, 18))
        as allocated_review_sample_size,
    cast(allocated_review_score as number(38, 18)) as allocated_review_score,
    cast(average_review_score as number(38, 6)) as average_review_score,
    cast(allocation_policy_version as varchar) as allocation_policy_version,
    cast('NON_ADDITIVE_ACROSS_PRODUCTS' as varchar) as order_count_usage,
    cast('NOT_AVAILABLE_UNTIL_M4' as varchar) as ai_enrichment_status,
    cast(metric_policy_version as varchar) as metric_policy_version,
    cast('reviewlens-semantic-catalog-v1' as varchar) as semantic_contract_version
from {{ ref('mart_product_review') }}
