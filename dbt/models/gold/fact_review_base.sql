{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__FACT_REVIEW_BASE') }}

with conformed as (
    select
        review.review_id,
        review.order_id,
        parent.order_key,
        parent.analysis_scope_status as order_analysis_scope_status,
        review.review_score,
        review.review_creation_date,
        review.review_answer_timestamp,
        review.review_text_present,
        review.response_latency_seconds,
        review.ai_eligibility_status,
        review.ai_eligible,
        review.dlp_projection_required,
        review.source_release_id,
        review.ingestion_batch_id,
        review.dataset_run_id,
        review.source_record_hash,
        review.ingested_at
    from {{ reviewlens_silver_candidate_relation('SIL_ORDER_REVIEW') }} as review
    inner join {{ ref('fact_order') }} as parent using (order_id)
    where review.order_parent_exists
      and review.response_interval_valid
      and review.review_score between 1 and 5
)

select
    cast(
        {{ reviewlens_gold_key(
            'REVIEW',
            "concat_ws(':', review_id, order_id)"
        ) }} as varchar
    ) as review_key,
    cast(order_key as varchar) as order_key,
    cast(review_id as varchar) as review_id,
    cast(order_id as varchar) as order_id,
    cast(to_number(to_char(review_creation_date, 'YYYYMMDD')) as number(38, 0))
        as review_date_key,
    cast(review_score as number(38, 0)) as review_score,
    cast(order_analysis_scope_status as varchar) as order_analysis_scope_status,
    cast(review_creation_date as timestamp_ntz(6)) as review_creation_date,
    cast(review_answer_timestamp as timestamp_ntz(6)) as review_answer_timestamp,
    cast(review_text_present as boolean) as review_text_present,
    cast(response_latency_seconds as number(38, 0)) as response_latency_seconds,
    cast(ai_eligibility_status as varchar) as ai_eligibility_status,
    cast(ai_eligible as boolean) as ai_eligible,
    cast(dlp_projection_required as boolean) as dlp_projection_required,
    cast(1 as number(38, 0)) as review_count,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(source_record_hash as varchar) as source_record_hash,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-fact-review-base-v1' as varchar) as model_contract_version
from conformed
