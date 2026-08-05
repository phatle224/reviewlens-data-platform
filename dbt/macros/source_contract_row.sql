{% macro source_contract_row(source_name, relation_name, source_file_name, expected_grain, source_ordinal) -%}
select
    cast('{{ source_name }}' as varchar) as source_name,
    cast('{{ relation_name }}' as varchar) as relation_name,
    cast('{{ source_file_name }}' as varchar) as source_file_name,
    cast('{{ expected_grain }}' as varchar) as expected_grain,
    cast({{ source_ordinal }} as number(38, 0)) as source_ordinal
{%- endmacro %}
