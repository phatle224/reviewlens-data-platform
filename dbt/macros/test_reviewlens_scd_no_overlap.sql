{% test reviewlens_scd_no_overlap(
    model,
    natural_key_column,
    effective_from_column='effective_from',
    effective_to_column='effective_to'
) %}
select
    older.{{ adapter.quote(natural_key_column | upper) }} as natural_key,
    older.{{ adapter.quote(effective_from_column | upper) }} as older_effective_from,
    newer.{{ adapter.quote(effective_from_column | upper) }} as newer_effective_from
from {{ model }} as older
inner join {{ model }} as newer
    on older.{{ adapter.quote(natural_key_column | upper) }}
        = newer.{{ adapter.quote(natural_key_column | upper) }}
   and older.{{ adapter.quote(effective_from_column | upper) }}
        < newer.{{ adapter.quote(effective_from_column | upper) }}
where coalesce(
    older.{{ adapter.quote(effective_to_column | upper) }},
    to_timestamp_ntz('9999-12-31 00:00:00')
) > newer.{{ adapter.quote(effective_from_column | upper) }}
{% endtest %}
