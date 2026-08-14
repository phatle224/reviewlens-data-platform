{% test reviewlens_scd_no_overlap(
    model,
    natural_key_column,
    effective_from_column='effective_from',
    effective_to_column='effective_to'
) %}
select
    older.{{ adapter.quote(natural_key_column) }} as natural_key,
    older.{{ adapter.quote(effective_from_column) }} as older_effective_from,
    newer.{{ adapter.quote(effective_from_column) }} as newer_effective_from
from {{ model }} as older
inner join {{ model }} as newer
    on older.{{ adapter.quote(natural_key_column) }}
        = newer.{{ adapter.quote(natural_key_column) }}
   and older.{{ adapter.quote(effective_from_column) }}
        < newer.{{ adapter.quote(effective_from_column) }}
where coalesce(
    older.{{ adapter.quote(effective_to_column) }},
    to_timestamp_ntz('9999-12-31 00:00:00')
) > newer.{{ adapter.quote(effective_from_column) }}
{% endtest %}
