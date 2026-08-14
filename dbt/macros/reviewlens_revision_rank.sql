{% macro reviewlens_revision_rank(partition_by, effective_at=none) -%}
row_number() over (
    partition by {{ partition_by }}
    order by
        {% if effective_at is not none %}{{ effective_at }} desc nulls last,{% endif %}
        ingested_at desc,
        source_row_number desc,
        record_hash desc
)
{%- endmacro %}
