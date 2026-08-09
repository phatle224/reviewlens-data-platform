#!/usr/bin/env bash
set -euo pipefail

airflow db migrate
airflow pools import /opt/reviewlens/airflow/pools.json
exec airflow standalone

