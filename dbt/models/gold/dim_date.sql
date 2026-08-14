{% set candidate_namespace = var('candidate_namespace', 'C_PARSE_ONLY') %}
{{ config(alias=candidate_namespace ~ '__DIM_DATE') }}

with event_dates as (
    select cast(order_purchase_timestamp as date) as full_date from {{ ref('sil_order') }}
    union select cast(order_approved_at as date) from {{ ref('sil_order') }}
    union select cast(order_delivered_carrier_date as date) from {{ ref('sil_order') }}
    union select cast(order_delivered_customer_date as date) from {{ ref('sil_order') }}
    union select cast(order_estimated_delivery_date as date) from {{ ref('sil_order') }}
    union select cast(shipping_limit_date as date) from {{ ref('sil_order_item') }}
    union select cast(review_creation_date as date) from {{ ref('sil_order_review') }}
    union select cast(review_answer_timestamp as date) from {{ ref('sil_order_review') }}
    union select to_date('1900-01-01')
), valid_dates as (
    select distinct full_date
    from event_dates
    where full_date is not null
)

select
    cast(to_number(to_char(full_date, 'YYYYMMDD')) as number(38, 0)) as date_key,
    cast(full_date as date) as full_date,
    cast(year(full_date) as number(38, 0)) as calendar_year,
    cast(quarter(full_date) as number(38, 0)) as calendar_quarter,
    cast(month(full_date) as number(38, 0)) as calendar_month,
    cast(monthname(full_date) as varchar) as month_name,
    cast(weekiso(full_date) as number(38, 0)) as iso_week,
    cast(day(full_date) as number(38, 0)) as day_of_month,
    cast(dayofweekiso(full_date) as number(38, 0)) as iso_day_of_week,
    cast(dayname(full_date) as varchar) as day_name,
    cast(date_trunc('week', full_date) as date) as week_start_date,
    cast(date_trunc('month', full_date) as date) as month_start_date,
    cast(date_trunc('quarter', full_date) as date) as quarter_start_date,
    cast('{{ var("source_release_id", "__REQUIRED_SOURCE_RELEASE_ID__") }}' as varchar)
        as source_release_id,
    cast('{{ var("ingestion_batch_id", "__REQUIRED_INGESTION_BATCH_ID__") }}' as varchar)
        as ingestion_batch_id,
    cast('reviewlens-dim-date-v1' as varchar) as model_contract_version
from valid_dates
