{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__SIL_UNKNOWN_MEMBER_REGISTRY') }}

with entity_types as (
    select column1 as entity_type
    from values ('CUSTOMER'), ('PRODUCT'), ('SELLER'), ('GEOGRAPHY')
)

select
    cast(
        sha2(concat('reviewlens-unknown-member-v1', chr(0), entity_type), 256) as varchar
    ) as unknown_member_key,
    cast(entity_type as varchar) as entity_type,
    cast('UNKNOWN' as varchar) as display_label,
    cast(to_timestamp_ntz('1900-01-01 00:00:00') as timestamp_ntz(6)) as effective_from,
    cast(null as timestamp_ntz(6)) as effective_to,
    cast(true as boolean) as is_current,
    cast('{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}' as varchar)
        as source_release_id,
    cast('{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}' as varchar)
        as ingestion_batch_id,
    cast('reviewlens-unknown-member-v1' as varchar) as unknown_policy_version,
    cast('reviewlens-sil-unknown-member-registry-v1' as varchar) as model_contract_version
from entity_types
