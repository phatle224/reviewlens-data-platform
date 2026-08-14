{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_DQ_QUARANTINE') }}

with order_findings as (
    select
        {{ reviewlens_dq_columns(
            "'SIL_ORDER'",
            'order_id',
            'analysis_scope_reason',
            "iff(analysis_scope_status = 'QUARANTINED', 'CRITICAL', 'QUARANTINE')"
        ) }}
    from {{ ref('sil_order') }}
    where analysis_scope_status in ('QUARANTINED', 'UNKNOWN')
), geolocation_findings as (
    select
        {{ reviewlens_dq_columns(
            "'SIL_GEOLOCATION_ZIP'",
            'geolocation_zip_prefix',
            'geolocation_quality_status',
            "'WARN'"
        ) }}
    from {{ ref('sil_geolocation_zip') }}
    where geolocation_quality_status != 'VALID'
), item_findings as (
    select
        {{ reviewlens_dq_columns(
            "'SIL_ORDER_ITEM'",
            "concat_ws(':', order_id, cast(order_item_id as varchar))",
            'amount_quality_status',
            "iff(amount_quality_status = 'ORPHAN_ORDER', 'CRITICAL', 'QUARANTINE')"
        ) }}
    from {{ ref('sil_order_item') }}
    where amount_quality_status != 'VALID'
), payment_findings as (
    select
        {{ reviewlens_dq_columns(
            "'SIL_ORDER_PAYMENT'",
            "concat_ws(':', order_id, cast(payment_sequential as varchar))",
            'amount_quality_status',
            "iff(amount_quality_status = 'ORPHAN_ORDER', 'CRITICAL', 'QUARANTINE')"
        ) }}
    from {{ ref('sil_order_payment') }}
    where amount_quality_status != 'VALID'
), product_findings as (
    select
        {{ reviewlens_dq_columns(
            "'SIL_PRODUCT'",
            'product_id',
            'product_quality_status',
            "'WARN'"
        ) }}
    from {{ ref('sil_product') }}
    where product_quality_status != 'VALID'
), seller_findings as (
    select
        {{ reviewlens_dq_columns(
            "'SIL_SELLER'",
            'seller_id',
            "iff(not geolocation_zip_exists, 'ZIP_NOT_FOUND', geolocation_quality_status)",
            "'WARN'"
        ) }}
    from {{ ref('sil_seller') }}
    where not geolocation_zip_exists or geolocation_quality_status != 'VALID'
), review_findings as (
    select
        {{ reviewlens_dq_columns(
            "'SIL_ORDER_REVIEW'",
            "concat_ws(':', review_id, order_id)",
            'ai_eligibility_status',
            "iff(ai_eligibility_status = 'ORPHAN_ORDER', 'CRITICAL', 'QUARANTINE')"
        ) }}
    from {{ ref('sil_order_review') }}
    where ai_eligibility_status in ('ORPHAN_ORDER', 'INVALID_RESPONSE_INTERVAL')
), all_findings as (
    select * from order_findings
    union all select * from geolocation_findings
    union all select * from item_findings
    union all select * from payment_findings
    union all select * from product_findings
    union all select * from seller_findings
    union all select * from review_findings
)

select *
from all_findings
