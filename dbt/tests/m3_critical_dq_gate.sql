{{ config(tags=['m3_critical'], severity='error') }}

select dq_event_id, model_name, grain_key_hash, dq_code
from {{ ref('sil_dq_quarantine') }}
where severity = 'CRITICAL'
