{% macro reviewlens_dq_columns(model_name, grain_expression, dq_code_expression, severity_expression) -%}
    cast(
        sha2(
            concat_ws(
                chr(0),
                'reviewlens-silver-dq-v1',
                {{ model_name }},
                coalesce(cast({{ grain_expression }} as varchar), '__NULL__'),
                {{ dq_code_expression }},
                source_release_id,
                ingestion_batch_id
            ),
            256
        ) as varchar
    ) as dq_event_id,
    cast({{ model_name }} as varchar) as model_name,
    cast(
        sha2(coalesce(cast({{ grain_expression }} as varchar), '__NULL__'), 256) as varchar
    ) as grain_key_hash,
    cast({{ dq_code_expression }} as varchar) as dq_code,
    cast({{ severity_expression }} as varchar) as severity,
    cast(source_release_id as varchar) as source_release_id,
    cast(ingestion_batch_id as varchar) as ingestion_batch_id,
    cast(dataset_run_id as varchar) as dataset_run_id,
    cast(ingested_at as timestamp_tz(6)) as observed_at,
    cast('reviewlens-silver-dq-v1' as varchar) as dq_contract_version
{%- endmacro %}
