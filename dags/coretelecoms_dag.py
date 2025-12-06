"""
Daily orchestration DAG for the CoreTelecoms capstone.
Ingests data from S3 (customers/call logs/social), Google Sheets (agents),
and Postgres (website forms) into a raw Parquet layer in S3.
"""

import os
import json
import tempfile
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.models import Variable
from airflow.operators.python import PythonOperator

from include.functions import (
    download_file_from_s3_to_local,
    upload_to_s3_as_parquet,
    postgres_to_s3_as_parquet,
)
from include.google_sheets import fetch_agents_sheet


DEFAULT_ARGS = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": pendulum.datetime(2025, 11, 20, tz="UTC"),
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


AWS_CONN_ID = "CDE_CAPSTONE_AWS_CONN"
POSTGRES_CONN_ID = "CORE_TELECOMS_POSTGRES_CONN"
G_SHEETS_CONN_ID = "GOOGLE_SHEETS_API_CONN"

SOURCE_BUCKET = "core-telecoms-data-lake"
DESTINATION_BUCKET = "core-telecoms-capstone-data-lake"
POSTGRES_SCHEMA = "customer_complaints"


def _call_logs_key(execution_date):
    ds = execution_date.strftime("%Y-%m-%d")
    return f"call logs/call_logs_day_{ds}.csv"


def _social_media_key(execution_date):
    ds = execution_date.strftime("%Y-%m-%d")
    return f"social_media/social_media_{ds}.json"


def fetch_customers(**_):
    return download_file_from_s3_to_local(
        aws_conn_id=AWS_CONN_ID,
        key="customers/customers_dataset.csv",
        bucket_name=SOURCE_BUCKET,
    )


def fetch_call_logs(execution_date, **_):
    return download_file_from_s3_to_local(
        aws_conn_id=AWS_CONN_ID,
        key=_call_logs_key(execution_date),
        bucket_name=SOURCE_BUCKET,
    )


def fetch_social_media(execution_date, **_):
    return download_file_from_s3_to_local(
        aws_conn_id=AWS_CONN_ID,
        key=_social_media_key(execution_date),
        bucket_name=SOURCE_BUCKET,
    )


def upload_customers(ti, **_):
    local_file = ti.xcom_pull(task_ids="fetch_customers")
    return upload_to_s3_as_parquet(
        aws_conn_id=AWS_CONN_ID,
        local_file_path=local_file,
        bucket_name=DESTINATION_BUCKET,
        s3_key="raw/customers/customers_dataset.parquet",
        mode="overwrite",
    )


def upload_call_logs(ti, **_):
    local_file = ti.xcom_pull(task_ids="fetch_call_logs")
    return upload_to_s3_as_parquet(
        aws_conn_id=AWS_CONN_ID,
        local_file_path=local_file,
        bucket_name=DESTINATION_BUCKET,
        s3_key="raw/call_logs/call_logs_dataset.parquet",
        mode="overwrite",
    )


def upload_social_media(ti, **_):
    local_file = ti.xcom_pull(task_ids="fetch_social_media")
    return upload_to_s3_as_parquet(
        aws_conn_id=AWS_CONN_ID,
        local_file_path=local_file,
        file_format="json",
        bucket_name=DESTINATION_BUCKET,
        s3_key="raw/social_media/social_media_dataset.parquet",
        mode="overwrite",
    )


def ingest_website_forms(execution_date, **_):
    table_suffix = execution_date.strftime("%Y_%m_%d")
    table_name = f"web_form_request_{table_suffix}"
    sql_query = f'SELECT * FROM "{POSTGRES_SCHEMA}"."{table_name}"'
    s3_key = f"raw/website_forms/{table_name}.parquet"

    return postgres_to_s3_as_parquet(
        aws_conn_id=AWS_CONN_ID,
        postgres_conn_id=POSTGRES_CONN_ID,
        sql_query=sql_query,
        bucket_name=DESTINATION_BUCKET,
        s3_key=s3_key,
        mode="overwrite",
    )


def ingest_agents(**_):
    gcp_conn = BaseHook.get_connection(G_SHEETS_CONN_ID)
    service_account_info = json.loads(
        gcp_conn.extra_dejson.get("extra__google_cloud_platform__keyfile_dict")
    )

    # Prefer Airflow Variable, fall back to env var for CI friendliness
    sheet_id = Variable.get(
        "AGENTS_SPREADSHEET_ID",
        default_var=os.getenv("AGENTS_SPREADSHEET_ID"),
    )
    if not sheet_id:
        raise ValueError("AGENTS_SPREADSHEET_ID must be set as a Variable or env var.")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp_file:
        local_csv_path = tmp_file.name

    fetch_agents_sheet(
        service_account_info=service_account_info,
        spreadsheet_id=sheet_id,
        sheet_name="agents",
        local_csv_path=local_csv_path,
    )

    return upload_to_s3_as_parquet(
        aws_conn_id=AWS_CONN_ID,
        local_file_path=local_csv_path,
        bucket_name=DESTINATION_BUCKET,
        s3_key="raw/agents/agents_dataset.parquet",
        mode="overwrite",
    )


with DAG(
    dag_id="coretelecoms_capstone",
    default_args=DEFAULT_ARGS,
    schedule="@daily",
    catchup=True,
    tags=["coretelecoms", "capstone", "ingestion"],
) as dag:
    fetch_customers_task = PythonOperator(
        task_id="fetch_customers",
        python_callable=fetch_customers,
    )

    fetch_call_logs_task = PythonOperator(
        task_id="fetch_call_logs",
        python_callable=fetch_call_logs,
    )

    fetch_social_media_task = PythonOperator(
        task_id="fetch_social_media",
        python_callable=fetch_social_media,
    )

    upload_customers_task = PythonOperator(
        task_id="upload_customers",
        python_callable=upload_customers,
    )

    upload_call_logs_task = PythonOperator(
        task_id="upload_call_logs",
        python_callable=upload_call_logs,
    )

    upload_social_media_task = PythonOperator(
        task_id="upload_social_media",
        python_callable=upload_social_media,
    )

    website_forms_task = PythonOperator(
        task_id="ingest_website_forms",
        python_callable=ingest_website_forms,
    )

    agents_task = PythonOperator(
        task_id="agents_google_sheet_to_s3",
        python_callable=ingest_agents,
        trigger_rule="all_done",
    )

    fetch_customers_task >> upload_customers_task
    fetch_call_logs_task >> upload_call_logs_task
    fetch_social_media_task >> upload_social_media_task
    agents_task
    website_forms_task
