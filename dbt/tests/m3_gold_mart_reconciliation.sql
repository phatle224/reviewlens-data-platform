{{ config(tags=['m3_gold_marts'], severity='error') }}

select 'ORDER_DELIVERY_ORDER_COUNT' as failure
where (select coalesce(sum(order_count), 0) from {{ ref('mart_order_delivery') }})
    != (select count(*) from {{ ref('fact_order') }})

union all

select 'ORDER_DELIVERY_GMV'
where (select coalesce(sum(gross_merchandise_value), 0) from {{ ref('mart_order_delivery') }})
    != (select coalesce(sum(price), 0) from {{ ref('fact_order_item') }})

union all

select 'ORDER_DELIVERY_FREIGHT'
where (select coalesce(sum(freight_value), 0) from {{ ref('mart_order_delivery') }})
    != (select coalesce(sum(freight_value), 0) from {{ ref('fact_order_item') }})

union all

select 'ORDER_DELIVERY_PAYMENT'
where (select coalesce(sum(payment_value), 0) from {{ ref('mart_order_delivery') }})
    != (select coalesce(sum(payment_value), 0) from {{ ref('fact_payment') }})

union all

select 'PRODUCT_ITEM_COUNT'
where (select coalesce(sum(item_count), 0) from {{ ref('mart_product_review') }})
    != (select count(*) from {{ ref('fact_order_item') }})

union all

select 'PRODUCT_REVIEW_COUNT'
where (select coalesce(sum(allocated_review_count), 0) from {{ ref('mart_product_review') }})
    != (
        select coalesce(sum(allocated_review_count), 0)
        from {{ ref('bridge_review_item_attribution') }}
    )

union all

select 'PRODUCT_REVIEW_SCORE'
where (select coalesce(sum(allocated_review_score), 0) from {{ ref('mart_product_review') }})
    != (
        select coalesce(sum(allocated_review_score), 0)
        from {{ ref('bridge_review_item_attribution') }}
    )

union all

select 'SELLER_ITEM_COUNT'
where (select coalesce(sum(item_count), 0) from {{ ref('mart_seller_performance') }})
    != (select count(*) from {{ ref('fact_order_item') }})

union all

select 'SELLER_REVIEW_COUNT'
where (select coalesce(sum(allocated_review_count), 0) from {{ ref('mart_seller_performance') }})
    != (
        select coalesce(sum(allocated_review_count), 0)
        from {{ ref('bridge_review_item_attribution') }}
    )

union all

select 'SELLER_REVIEW_SCORE'
where (select coalesce(sum(allocated_review_score), 0) from {{ ref('mart_seller_performance') }})
    != (
        select coalesce(sum(allocated_review_score), 0)
        from {{ ref('bridge_review_item_attribution') }}
    )

union all

select 'CUSTOMER_ORDER_COUNT'
where (select coalesce(sum(order_count), 0) from {{ ref('mart_customer_overview') }})
    != (select count(*) from {{ ref('fact_order') }})

union all

select 'CUSTOMER_GMV'
where (select coalesce(sum(gross_merchandise_value), 0) from {{ ref('mart_customer_overview') }})
    != (select coalesce(sum(price), 0) from {{ ref('fact_order_item') }})

union all

select 'CUSTOMER_PAYMENT'
where (select coalesce(sum(payment_value), 0) from {{ ref('mart_customer_overview') }})
    != (select coalesce(sum(payment_value), 0) from {{ ref('fact_payment') }})
