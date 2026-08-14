{% test reviewlens_expression_is_true(model, expression, column_name=none) %}
select *
from {{ model }}
where not coalesce({{ expression }}, false)
{% endtest %}
