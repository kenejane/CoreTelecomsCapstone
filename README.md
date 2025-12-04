# CoreTelecoms Unified Customer Experience Platform

Production-grade data platform that ingests complaints data from multiple channels (S3 CSV/JSON, Google Sheets, Postgres) into an S3 raw layer, models it into BigQuery via dbt, and orchestrates everything with Apache Airflow running in Docker.

## Architecture (conceptual)
- Airflow (CeleryExecutor) orchestrates extraction from S3 buckets, transactional Postgres, and Google Sheets.
- Raw data is landed in an S3 data lake as Parquet with load metadata.
- dbt targets BigQuery (sample Terraform provided) to build curated marts (e.g., fact_complaints) for analytics/ML.
- Terraform provisions cloud infra (S3 data lake, BigQuery dataset/tables, IAM/region configs). State should be stored remotely (configure your backend).
- CI/CD: build the Airflow image, run lint/tests, then push the image to your container registry.

## Repo layout
- `dags/coretelecoms_dag.py` – Airflow DAG wiring daily ingestion for all sources.
- `include/functions.py` – shared S3/Postgres helpers with Airflow connections.
- `include/google_sheets.py` – helper to pull the agents sheet with a service account.
- `docker-compose.yaml` – local Airflow stack (CeleryExecutor, Postgres metadata, Redis).
- `Dockerfile` – custom Airflow image with required providers and dbt.
- `requirements.txt` – Python deps for Airflow image and tasks.
- `resources.tf`, `providers.tf` – sample AWS data lake provisioning (S3 with versioning).
- `bigquery.tf` – sample BigQuery dataset/tables/view for dbt modelling.
- `terraform.tfstate*` – local state files (switch to remote backend in production).

## Airflow DAG overview
- **DAG id:** `coretelecoms_capstone`
- **Schedule:** daily (catchup enabled) starting 2025-11-20 UTC.
- **Sources:**  
  - S3 `core-telecoms-data-lake`: customers (static CSV), call logs (daily CSV), social media (daily JSON).  
  - Google Sheets: agents lookup (must copy to your private sheet).  
  - Postgres schema `customer_complaints`: daily tables `web_form_request_YYYY_MM_DD`.
- **Target:** S3 bucket `core-telecoms-capstone-data-lake` under `raw/<domain>/...` as Parquet.
- **Connections (set in Airflow UI or env):**  
  - `CDE_CAPSTONE_AWS_CONN` – AWS access key/secret + region in extra.  
  - `CORE_TELECOMS_POSTGRES_CONN` – Postgres host/port/user/password/db.  
  - `GOOGLE_SHEETS_API_CONN` – extra contains `extra__google_cloud_platform__keyfile_dict` JSON for the service account.  
  - Variable `AGENTS_SPREADSHEET_ID` – your private sheet ID (or env var of same name).
- **S3 key templates:**  
  - Call logs: `call logs/call_logs_day_<ds>.csv`  
  - Social media: `social_media/social_media_<ds>.json` (update to match your bucket layout).  
  - Web forms: table `web_form_request_<YYYY_MM_DD>` in Postgres.

## Local run (or CI)
1) Export an Airflow UID (recommended on Linux): `echo "AIRFLOW_UID=$(id -u)" > .env`  
2) Build and start: `docker compose up --build -d`  
3) Access Airflow UI: http://localhost:8080 (user/pass from `_AIRFLOW_WWW_USER_*` envs, defaults `airflow/airflow`).  
4) Create the three connections + variable in the UI or via env vars.  
5) Trigger the DAG manually to backfill the specified start date range.

## Building and pushing the image
```
docker build -t <registry>/coretelecoms-airflow:latest .
docker push <registry>/coretelecoms-airflow:latest
```
Update `AIRFLOW_IMAGE_NAME` in `docker-compose.yaml` or your deployment manifests to pull the pushed image.

## Terraform
- AWS data lake: see `resources.tf` for an S3 bucket with versioning in `eu-north-1`.
- BigQuery warehouse: `bigquery.tf` provisions dataset `coretelecoms_raw`, staging tables, and a modelled `fact_complaints` view. Variables to provide:
  - `gcp_project_id` (required), `gcp_region` (default `europe-north1`), `bq_default_location` (default `EU`).
- Providers: `providers.tf` includes both AWS and Google. Configure a remote backend for state before applying in a team setting.

Example apply:
```
terraform init
terraform plan -var="gcp_project_id=<project>" -var="gcp_region=europe-north1"
terraform apply -auto-approve -var="gcp_project_id=<project>" -var="gcp_region=europe-north1"
```

## dbt (BigQuery target)
- Profiles: point `outputs.prod` to the dataset created by Terraform (`coretelecoms_raw`) and reuse the service account used by Airflow/Google provider.
- Models: start with staging models reading S3-landed parquet via external tables or after loading to BigQuery; build marts like `fact_complaints` (see view SQL in `bigquery.tf` as a starting point).

## Credentials guidance
- AWS: do **not** commit keys. Use Airflow connections and IAM roles where possible.
- Google Sheets: copy the shared agents sheet into your own Google Drive, create a service account, share the sheet with the service account email, and paste the JSON key into the Airflow connection extra.
- Postgres: store connection string in Airflow connection `CORE_TELECOMS_POSTGRES_CONN` and rotate regularly.

## Next steps / hardening
- Add Slack/Teams alerting via Airflow on failure.
- Add data quality checks (Great Expectations or dbt tests) in downstream tasks.
- Wire CI to run `airflow dags test`, linting, and `terraform fmt/validate`.
- Move Terraform state to a remote backend (S3/GCS) and add workspaces for envs.
