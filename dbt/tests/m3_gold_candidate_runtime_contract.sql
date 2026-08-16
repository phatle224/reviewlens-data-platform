{{ config(tags=['m3_gold_candidate'], severity='error') }}

select 'invalid_m3_gold_candidate_runtime_contract' as failure
where not regexp_like(
    '{{ var("candidate_namespace", "C_PARSE_ONLY") }}',
    '^C_[A-F0-9]{64}$'
)
   or not regexp_like(
       '{{ var("silver_candidate_namespace", "C_PARSE_ONLY") }}',
       '^C_[A-F0-9]{64}$'
   )
   or '{{ var("candidate_namespace", "C_PARSE_ONLY") }}'
       = '{{ var("silver_candidate_namespace", "C_PARSE_ONLY") }}'
   or not regexp_like(
       '{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}',
       '^olist_[0-9a-f]{64}$'
   )
   or not regexp_like(
       '{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}',
       '^batch_[0-9a-f]{64}$'
   )
