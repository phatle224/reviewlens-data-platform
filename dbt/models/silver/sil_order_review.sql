{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_ORDER_REVIEW') }}

with ranked_review as (
    select
        review_id,
        order_id,
        review_score,
        review_comment_title,
        review_comment_message,
        review_creation_date,
        review_answer_timestamp,
        source_release_id,
        ingestion_batch_id,
        dataset_run_id,
        record_hash,
        source_row_number,
        ingested_at,
        {{ reviewlens_revision_rank('review_id, order_id') }} as source_rank
    from {{ source('bronze_olist', 'order_reviews') }}
    where source_release_id = '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}'
      and ingestion_batch_id = '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}'
), joined as (
    select
        source_review.* exclude source_rank,
        parent_order.order_id is not null as order_parent_exists,
        parent_order.analysis_scope_status,
        length(trim(coalesce(review_comment_title, '')))
            + length(trim(coalesce(review_comment_message, ''))) as review_text_length,
        review_answer_timestamp >= review_creation_date as response_interval_valid
    from ranked_review as source_review
    left join {{ ref('sil_order') }} as parent_order using (order_id)
    where source_rank = 1
)

select
    cast(review_id as varchar) as review_id,
    cast(order_id as varchar) as order_id,
    cast(review_score as number(38, 0)) as review_score,
    cast(review_comment_title as varchar) as review_comment_title,
    cast(review_comment_message as varchar) as review_comment_message,
    cast(review_creation_date as timestamp_ntz(6)) as review_creation_date,
    cast(review_answer_timestamp as timestamp_ntz(6)) as review_answer_timestamp,
    cast(order_parent_exists as boolean) as order_parent_exists,
    cast(review_text_length > 0 as boolean) as review_text_present,
    cast(review_text_length as number(38, 0)) as review_text_length,
    cast(response_interval_valid as boolean) as response_interval_valid,
    cast(
        iff(
            response_interval_valid,
            datediff('second', review_creation_date, review_answer_timestamp),
            null
        ) as number(38, 0)
    ) as response_latency_seconds,
    cast(
        case
            when not response_interval_valid then 'INVALID_RESPONSE_INTERVAL'
            when not order_parent_exists then 'ORPHAN_ORDER'
            when analysis_scope_status != 'IN_SCOPE' then 'OUT_OF_SCOPE_ORDER'
            when review_text_length = 0 then 'SCORE_ONLY'
            else 'PENDING_DLP'
        end as varchar
    ) as ai_eligibility_status,
    cast(false as boolean) as ai_eligible,
    cast(review_text_length > 0 as boolean) as dlp_projection_required,
    cast('review-ai-eligibility-v1' as varchar) as eligibility_policy_version,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(record_hash as varchar) as source_record_hash,
    cast(source_row_number as number(38, 0)) as source_row_number,
    cast(ingested_at as timestamp_tz(6)) as ingested_at,
    cast('reviewlens-sil-order-review-v1' as varchar) as model_contract_version
from joined
