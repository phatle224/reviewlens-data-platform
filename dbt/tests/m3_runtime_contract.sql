{{ config(tags=['m3_silver']) }}

select 'invalid_m3_runtime_contract' as failure
where not regexp_like(
    '{{ var("candidate_namespace", "C_PARSE_ONLY") }}',
    '^C_[A-F0-9]{64}$'
)
   or not regexp_like(
       '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}',
       '^olist_[0-9a-f]{64}$'
   )
   or not regexp_like(
       '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}',
       '^batch_[0-9a-f]{64}$'
   )
