import tempfile
import json

import awswrangler as wr
import boto3
import pandas as pd
from botocore.exceptions import ClientError
from airflow.hooks.base import BaseHook
from airflow.providers.postgres.hooks.postgres import PostgresHook


# -----------------------------
# AWS S3 CLIENT USING UI CONNECTION
# -----------------------------
def get_s3_client(aws_conn_id):
    """
    Returns boto3 S3 client using Airflow connection defined in UI.
    """
    try:
        conn = BaseHook.get_connection(aws_conn_id)
        region = conn.extra_dejson.get("region_name", "eu-north-1")
        session = boto3.Session(
            aws_access_key_id=conn.login,
            aws_secret_access_key=conn.password,
            region_name=region,
        )
        return session.client("s3")
    except Exception as e:
        print(f"Failed to create S3 client from connection {aws_conn_id}: {e}")
        # Fallback to default boto3 session if the Airflow connection is missing
        return boto3.client("s3")


# -----------------------------
# DOWNLOAD FILE FROM S3
# -----------------------------
def download_file_from_s3_to_local(aws_conn_id, key, bucket_name, local_path=None):
    s3_client = get_s3_client(aws_conn_id)

    if local_path is None:
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp_file:
            local_path = tmp_file.name

    print(f"Downloading s3://{bucket_name}/{key} to {local_path}")
    try:
        s3_client.download_file(bucket_name, key, local_path)
        print(f"✓ Download successful: {local_path}")
        return local_path
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        print(f"Download failed: {error_code} - {error_msg}")
        raise


# -----------------------------
# UPLOAD TO S3 AS PARQUET
# -----------------------------
def upload_to_s3_as_parquet(
    aws_conn_id,
    bucket_name,
    s3_key,
    local_file_path=None,
    df=None,
    mode="overwrite",
    file_format="csv",
):
    if local_file_path and df:
        raise ValueError("Provide either local_file_path or df, not both.")
    if df is not None and not isinstance(df, pd.DataFrame):
        raise ValueError("df must be a pandas DataFrame")

    if local_file_path:
        if file_format == "csv":
            df = pd.read_csv(local_file_path)
        elif file_format == "json":
            df = pd.read_json(local_file_path, lines=True)
        else:
            raise ValueError("Unsupported file_format; use 'csv' or 'json'.")

    s3_client = get_s3_client(aws_conn_id)
    credentials = getattr(s3_client._request_signer, "_credentials", None)

    if credentials:
        boto3_session = boto3.Session(
            aws_access_key_id=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_session_token=credentials.token,
            region_name=s3_client.meta.region_name
        )
    else:
        boto3_session = boto3.Session()

    s3_path = f"s3://{bucket_name}/{s3_key}"
    print(f"Uploading to {s3_path} (mode={mode})")

    try:
        result = wr.s3.to_parquet(
            df=df,
            path=s3_path,
            compression="snappy",
            dataset=True,
            mode=mode,
            boto3_session=boto3_session
        )
        print(f"✓ Upload successful: {s3_path}")
        return result
    except Exception as e:
        print(f"Upload failed: {e}")
        raise


# -----------------------------
# POSTGRES TO S3 AS PARQUET
# -----------------------------
def postgres_to_s3_as_parquet(aws_conn_id, postgres_conn_id, sql_query, bucket_name, s3_key, mode="overwrite"):
    print(f"Querying Postgres: {sql_query}")
    pg_hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    df = pg_hook.get_pandas_df(sql_query)
    print(f"Retrieved {len(df)} rows from Postgres")

    return upload_to_s3_as_parquet(
        aws_conn_id=aws_conn_id,
        bucket_name=bucket_name,
        s3_key=s3_key,
        df=df,
        mode=mode
    )
