{% macro reviewlens_silver_candidate_relation(logical_name) -%}
    {%- set candidate_namespace = var(
        'silver_candidate_namespace',
        var('candidate_namespace', 'C_PARSE_ONLY')
    ) -%}
    {{ adapter.quote(target.database) }}.{{ adapter.quote('SILVER') }}.
    {{ adapter.quote(candidate_namespace ~ '__' ~ logical_name) }}
{%- endmacro %}
