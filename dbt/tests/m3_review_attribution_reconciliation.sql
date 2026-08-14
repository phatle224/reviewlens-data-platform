{{ config(tags=['m3_review_attribution'], severity='error') }}

with reconciled as (
    select
        review_key,
        count(*) as attribution_row_count,
        max(item_count_for_review) as item_count_for_review,
        sum(allocation_weight) as allocation_weight,
        sum(allocated_review_count) as allocated_review_count,
        sum(allocated_review_score) as allocated_review_score,
        max(review_score) as review_score,
        count(distinct allocation_policy_version) as policy_version_count
    from {{ ref('bridge_review_item_attribution') }}
    group by review_key
)

select review_key
from reconciled
where allocation_weight != cast(1 as number(38, 18))
   or allocated_review_count != cast(1 as number(38, 18))
   or allocated_review_score != cast(review_score as number(38, 18))
   or policy_version_count != 1
   or attribution_row_count != greatest(item_count_for_review, 1)

union all

select sha2('REVIEW_ATTRIBUTION_SET_MISMATCH', 256)
where (select count(*) from reconciled)
    != (select count(*) from {{ ref('fact_review_base') }})
