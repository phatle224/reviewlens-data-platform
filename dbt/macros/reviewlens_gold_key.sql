{% macro reviewlens_gold_key(entity_type, natural_key_expression, version_expression=none) -%}
sha2(
    concat(
        'reviewlens-gold-key-v1',
        chr(0),
        '{{ entity_type }}',
        chr(0),
        cast({{ natural_key_expression }} as varchar)
        {% if version_expression is not none %}, chr(0), cast({{ version_expression }} as varchar){% endif %}
    ),
    256
)
{%- endmacro %}
