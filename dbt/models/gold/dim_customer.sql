{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__DIM_CUSTOMER') }}

with unknown_keys as (
    select
        max(iff(entity_type = 'CUSTOMER', unknown_member_key, null)) as customer_key,
        max(iff(entity_type = 'GEOGRAPHY', unknown_member_key, null)) as geography_key,
        min(source_release_id) as source_release_id,
        min(ingestion_batch_id) as ingestion_batch_id
    from {{ reviewlens_silver_candidate_relation('SIL_UNKNOWN_MEMBER_REGISTRY') }}
), source_customer as (
    select
        {{ reviewlens_gold_key(
            'CUSTOMER',
            'customer.customer_id',
            'customer.source_record_hash'
        ) }} as customer_key,
        customer.customer_id,
        customer.repeat_customer_key,
        coalesce(geography.geography_key, unknown_keys.geography_key) as geography_key,
        customer.customer_zip_prefix,
        customer.customer_city,
        customer.customer_state,
        customer.source_release_id,
        customer.ingestion_batch_id,
        customer.source_record_hash,
        customer.ingested_at as observed_at
    from {{ reviewlens_silver_candidate_relation('SIL_CUSTOMER') }} as customer
    cross join unknown_keys
    left join {{ ref('dim_geography') }} as geography
        on customer.customer_zip_prefix = geography.geolocation_zip_prefix
       and geography.is_current
), unknown_customer as (
    select
        customer_key,
        '__UNKNOWN__' as customer_id,
        customer_key as repeat_customer_key,
        geography_key,
        '__UNKNOWN__' as customer_zip_prefix,
        'UNKNOWN' as customer_city,
        'UNKNOWN' as customer_state,
        source_release_id,
        ingestion_batch_id,
        cast(null as varchar) as source_record_hash,
        cast(null as timestamp_tz(6)) as observed_at
    from unknown_keys
), conformed as (
    select * from source_customer
    union all
    select * from unknown_customer
)

select
    cast(customer_key as varchar) as customer_key,
    cast(customer_id as varchar) as customer_id,
    cast(repeat_customer_key as varchar) as repeat_customer_key,
    cast(geography_key as varchar) as geography_key,
    cast(customer_zip_prefix as varchar) as customer_zip_prefix,
    cast(customer_city as varchar) as customer_city,
    cast(customer_state as varchar) as customer_state,
    cast(to_timestamp_ntz('1900-01-01 00:00:00') as timestamp_ntz(6)) as effective_from,
    cast(null as timestamp_ntz(6)) as effective_to,
    cast(true as boolean) as is_current,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(source_record_hash as varchar) as source_record_hash,
    cast(observed_at as timestamp_tz(6)) as observed_at,
    cast('reviewlens-gold-history-v1' as varchar) as history_policy_version,
    cast('reviewlens-dim-customer-v1' as varchar) as model_contract_version
from conformed
