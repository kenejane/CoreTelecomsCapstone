import sys
sys.path.insert(0, '/opt/airflow/dags')

from datetime import timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
import pendulum
import pandas as pd
import json
from airflow.hooks.base import BaseHook
import awswrangler as wr

from CoreTelecomsCapstone.include.functions import (
    download_file_from_s3_to_local,
    upload_to_s3_as_parquet,
    postgres_to_s3_as_parquet
)

# -----------------------------
# Default DAG args
# -----------------------------
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': pendulum.datetime(2025, 12, 1),
    'retries': 2,
    'retry_delay': timedelta(minutes=5)
}

# -----------------------------
# DAG definition
# -----------------------------
with DAG(
    dag_id="CoreTelecomsCapstone",
    default_args=default_args,
    schedule='@daily',
    catchup=True,
    tags=["Coretelecoms", "capstone"],
) as dag:

    # -----------------------------
    # Connection IDs & S3 bucket
    # -----------------------------
    AWS_CONN_ID = "CDE_CAPSTONE_AWS_CONN"
    POSTGRES_CONN_ID = "CORE_TELECOMS_POSTGERES_CONN"
    SOURCE_BUCKET = "core-telecoms-data-lake"
    DESTINATION_BUCKET = "core-telecoms-capstone-data-lake"

    # -----------------------------
    # Wrapper functions
    # -----------------------------
    def fetch_customers_wrapper(**kwargs):
        return download_file_from_s3_to_local(
            aws_conn_id=AWS_CONN_ID,
            key="customers/customers_dataset.csv",
            bucket_name=SOURCE_BUCKET
        )

    def fetch_call_logs_wrapper(**kwargs):
        return download_file_from_s3_to_local(
            aws_conn_id=AWS_CONN_ID,
            key="call logs/call_logs_day_2025-11-23.csv",
            bucket_name=SOURCE_BUCKET
        )

    def fetch_social_media_wrapper(**kwargs):
        return download_file_from_s3_to_local(
            aws_conn_id=AWS_CONN_ID,
            key="social_medias/call_logs_day_2025-11-23.csv",
            bucket_name=SOURCE_BUCKET
        )

    def upload_customers_wrapper(**kwargs):
        ti = kwargs['ti']
        filename = ti.xcom_pull(task_ids='fetch_customers_task')
        return upload_to_s3_as_parquet(
            aws_conn_id=AWS_CONN_ID,
            local_file_path=filename,
            bucket_name=DESTINATION_BUCKET,
            s3_key="customers/customers_dataset.parquet",
            mode="overwrite"
        )

    def upload_call_logs_wrapper(**kwargs):
        ti = kwargs['ti']
        filename = ti.xcom_pull(task_ids='fetch_call_logs_task')
        return upload_to_s3_as_parquet(
            aws_conn_id=AWS_CONN_ID,
            local_file_path=filename,
            bucket_name=DESTINATION_BUCKET,
            s3_key="call_logs/call_logs_dataset.parquet",
            mode="overwrite"
        )

    def upload_social_media_wrapper(**kwargs):
        ti = kwargs['ti']
        filename = ti.xcom_pull(task_ids='fetch_social_media_task')
        return upload_to_s3_as_parquet(
            aws_conn_id=AWS_CONN_ID,
            local_file_path=filename,
            bucket_name=DESTINATION_BUCKET,
            s3_key="social_medias/social_media_dataset.parquet",
            mode="overwrite"
        )

    def website_forms_wrapper(**kwargs):
        return postgres_to_s3_as_parquet(
            aws_conn_id=AWS_CONN_ID,
            postgres_conn_id=POSTGRES_CONN_ID,
            sql_query="SELECT * FROM your_customer_complaints.web_form_request_2025_11_20",
            bucket_name= DESTINATION_BUCKET,
            s3_key="website_forms/web_form_request_2025_11_20.parquet",
            mode="overwrite"
        )

    # -----------------------------
    # Google Sheets wrapper
    # -----------------------------
    def upload_agents_wrapper(**kwargs):
        from oauth2client.service_account import ServiceAccountCredentials
        import gspread
        ti = kwargs['ti']

        # Get service account JSON from Airflow connection
        gcp_conn = BaseHook.get_connection("GOOGLE_SHEETS_API_CONN")
        service_account_info = json.loads(
            gcp_conn.extra_dejson.get("extra__google_cloud_platform__keyfile_dict")
        )

        scope = ['https://www.googleapis.com/auth/spreadsheets']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
        client = gspread.authorize(creds)

        sheet_id = "platinum-music-479514-s4"  # Replace with Variable.get if dynamic
        sheet_name = "agents"
        sheet = client.open_by_key(sheet_id).worksheet(sheet_name)

        records = sheet.get_all_records()
        df = pd.DataFrame(records)

        # Save locally & upload to S3
        local_csv = "/tmp/agents.csv"
        df.to_csv(local_csv, index=False)

        s3_key = "agents/agents_dataset.parquet"
        wr.s3.to_parquet(df, path=f"s3://{DESTINATION_BUCKET}/{s3_key}", dataset=True, mode="overwrite")

        # Push paths to XCom
        ti.xcom_push(key="agents_local_csv", value=local_csv)
        ti.xcom_push(key="agents_s3_path", value=f"s3://{DESTINATION_BUCKET}/{s3_key}")

        return f"s3://{DESTINATION_BUCKET}/{s3_key}"

    # -----------------------------
    # Tasks
    # -----------------------------
    fetch_customers_task = PythonOperator(
        task_id='fetch_customers_task',
        python_callable=fetch_customers_wrapper,
    )

    fetch_call_logs_task = PythonOperator(
        task_id='fetch_call_logs_task',
        python_callable=fetch_call_logs_wrapper,
    )

    fetch_social_media_task = PythonOperator(
        task_id='fetch_social_media_task',
        python_callable=fetch_social_media_wrapper,
    )

    upload_customers_task = PythonOperator(
        task_id='upload_customers_task',
        python_callable=upload_customers_wrapper,
    )

    upload_call_logs_task = PythonOperator(
        task_id='upload_call_logs_task',
        python_callable=upload_call_logs_wrapper,
    )

    upload_social_media_task = PythonOperator(
        task_id='upload_social_media_task',
        python_callable=upload_social_media_wrapper,
    )

    website_forms_task = PythonOperator(
        task_id='website_forms_task',
        python_callable=website_forms_wrapper,
    )

    agents_task = PythonOperator(
        task_id='agents_google_sheet_to_s3',
        python_callable=upload_agents_wrapper,
    )

    # -----------------------------
    # Task dependencies
    # -----------------------------
    fetch_customers_task >> upload_customers_task
    fetch_call_logs_task >> upload_call_logs_task
    fetch_social_media_task >> upload_social_media_task
    agents_task 
    website_forms_task
