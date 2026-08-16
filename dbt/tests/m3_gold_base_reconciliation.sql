{{ config(tags=['m3_gold_base'], severity='error') }}

select 'FACT_ORDER_COUNT' as failure
where (select count(*) from {{ ref('fact_order') }})
    != (
        select count(*)
        from {{ reviewlens_silver_candidate_relation('SIL_ORDER') }}
        where analysis_scope_status != 'QUARANTINED'
    )

union all

select 'FACT_ORDER_ITEM_COUNT'
where (select count(*) from {{ ref('fact_order_item') }})
    != (
        select count(*)
        from {{ reviewlens_silver_candidate_relation('SIL_ORDER_ITEM') }} as item
        inner join {{ ref('fact_order') }} as parent using (order_id)
        where item.order_parent_exists and item.amount_quality_status = 'VALID'
    )

union all

select 'FACT_PAYMENT_COUNT'
where (select count(*) from {{ ref('fact_payment') }})
    != (
        select count(*)
        from {{ reviewlens_silver_candidate_relation('SIL_ORDER_PAYMENT') }} as payment
        inner join {{ ref('fact_order') }} as parent using (order_id)
        where payment.order_parent_exists and payment.amount_quality_status = 'VALID'
    )

union all

select 'FACT_REVIEW_BASE_COUNT'
where (select count(*) from {{ ref('fact_review_base') }})
    != (
        select count(*)
        from {{ reviewlens_silver_candidate_relation('SIL_ORDER_REVIEW') }} as review
        inner join {{ ref('fact_order') }} as parent using (order_id)
        where review.order_parent_exists
          and review.response_interval_valid
          and review.review_score between 1 and 5
    )

union all

select 'FACT_ORDER_ITEM_AMOUNT'
where (select coalesce(sum(item_total_value), 0) from {{ ref('fact_order_item') }})
    != (
        select coalesce(sum(item.item_total_value), 0)
        from {{ reviewlens_silver_candidate_relation('SIL_ORDER_ITEM') }} as item
        inner join {{ ref('fact_order') }} as parent using (order_id)
        where item.order_parent_exists and item.amount_quality_status = 'VALID'
    )

union all

select 'FACT_PAYMENT_AMOUNT'
where (select coalesce(sum(payment_value), 0) from {{ ref('fact_payment') }})
    != (
        select coalesce(sum(payment.payment_value), 0)
        from {{ reviewlens_silver_candidate_relation('SIL_ORDER_PAYMENT') }} as payment
        inner join {{ ref('fact_order') }} as parent using (order_id)
        where payment.order_parent_exists and payment.amount_quality_status = 'VALID'
    )
