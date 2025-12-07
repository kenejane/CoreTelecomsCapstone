# CoreTelecoms Unified Customer Experience Platform

A production-grade **ELT data platform** for ingesting customer complaints data from multiple channels into an S3 data lake, modelling it in BigQuery using dbt, and orchestrating the entire workflow with Apache Airflow running in Docker.

---

## Architecture Overview (ELT – Medallion Pattern)

![ELT Medallion Architecture](docs/image.png)

### Conceptual Summary
- Apache Airflow (CeleryExecutor) orchestrates extraction from S3 buckets, transactional Postgres, and Google Sheets.
- Raw data is landed in an Amazon S3 data lake as Parquet with load metadata.
- Data is loaded into BigQuery following the **Bronze → Silver → Gold** medallion architecture.
- dbt performs all transformations **inside BigQuery**.
- Terraform provisions cloud infrastructure (S3, BigQuery, IAM, regions).
- CI/CD builds and pushes the Airflow image after linting and tests.

---

## End-to-End Data Flow

### 1. Data Sources
Customer complaints data originates from multiple heterogeneous sources:
- AWS S3 files (CSV / JSON)
- Google Sheets (via service account)
- Postgres transactional database
- External APIs

---

### 2. Orchestration — Apache Airflow
Apache Airflow (running on **CeleryExecutor** inside Docker) orchestrates the entire pipeline:
- Scheduling and backfills
- Retry and failure handling
- Task dependencies
- Triggering downstream dbt transformations

> Airflow **does not perform transformations**; it strictly manages workflow execution.

---

### 3. Raw Landing Zone — Amazon S3
All extracted data is first written into **Amazon S3**, which acts as the raw data lake.

**Raw layer characteristics:**
- Stored in Parquet format
- Immutable and replayable
- Schema-on-read
- Includes ingestion metadata (load timestamp, source system)

---

### 4. Bronze Layer — BigQuery (Raw Warehouse Tables)
Data from S3 is loaded into **BigQuery Bronze tables**.

**Bronze layer principles:**
- Minimal processing
- One-to-one mapping with raw data
- Warehouse source of truth
- No business logic applied

This completes the **Extract + Load** phases of ELT.

---

### 5. Silver Layer — Clean & Conformed Data (dbt)
dbt performs transformations **inside BigQuery** to produce cleaned datasets.

**Silver layer responsibilities:**
- Type casting
- Deduplication
- Standardized schemas
- Data quality fixes

Example:
coretelecoms_silver.complaints_clean

---

### 6. Gold Layer — Analytics-Ready Data (dbt)
The Gold layer contains **business-ready models** optimized for reporting, dashboards, and ML workloads.

**Gold layer responsibilities:**
- Business logic
- Aggregations
- Fact and dimension tables
- Query-optimized structures

Example:
coretelecoms_gold.fact_complaints

All Silver and Gold transformations are fully managed by **dbt**, with Airflow only responsible for triggering execution.

---

## Airflow DAG Overview

- **DAG ID:** `coretelecoms_capstone`
- **Schedule:** Daily (catchup enabled) starting `2025-11-20 UTC`

### Sources
- **Amazon S3 – `core-telecoms-data-lake`**
  - Customers (static CSV)
  - Call logs (daily CSV)
  - Social media (daily JSON)
- **Google Sheets**
  - Agents lookup (copied to a private sheet)
- **Postgres**
  - Schema: `customer_complaints`
  - Daily tables: `web_form_request_YYYY_MM_DD`

### Target
- **Amazon S3**
  - Bucket: `core-telecoms-capstone-data-lake`
  - Path: `raw/<domain>/...`
  - Format: Parquet

### Connections (Airflow)
- `CDE_CAPSTONE_AWS_CONN` – AWS access key, secret, region (extras)
- `CORE_TELECOMS_POSTGRES_CONN` – Postgres connection
- `GOOGLE_SHEETS_API_CONN` – Service account JSON in `extra__google_cloud_platform__keyfile_dict`
- Variable: `AGENTS_SPREADSHEET_ID`

### S3 Key Templates
- Call logs: `call_logs/call_logs_day_<ds>.csv`
- Social media: `social_media/social_media_<ds>.json`
- Web forms: `web_form_request_<YYYY_MM_DD>` (Postgres tables)

---

## Component Responsibilities

| Component | Responsibility |
|--------|----------------|
| Apache Airflow | Scheduling, orchestration, retries |
| Amazon S3 | Raw, immutable data landing |
| BigQuery Bronze | Raw warehouse ingestion |
| BigQuery Silver | Cleaned and conformed data |
| BigQuery Gold | Analytics-ready business data |
| dbt | Transformations, tests, lineage |
| Docker | Environment consistency |

---

## Repository Structure

- `dags/coretelecoms_dag.py` – Airflow DAG orchestrating ingestion and loads  
- `include/functions.py` – Shared helpers for S3 and Postgres access  
- `include/google_sheets.py` – Google Sheets ingestion via service account  
- `docker-compose.yaml` – Local Airflow stack (CeleryExecutor, Redis, Postgres metadata DB)  
- `Dockerfile` – Custom Airflow image including dbt and providers  
- `requirements.txt` – Python dependencies  
- `resources.tf`, `providers.tf` – AWS infrastructure provisioning  
- `bigquery.tf` – BigQuery Bronze/Silver/Gold datasets  
- `docs/image.png` – Architecture diagram  

---

## Local Run (or CI)

1. Export Airflow UID:
```bash
echo "AIRFLOW_UID=$(id -u)" > .env

2.	Build and start:
  docker compose up --build -d

3.	Access Airflow UI:
http://localhost:8080
(Default: airflow / airflow)

4.	Create required Airflow connections and variables.

5.	Trigger the DAG manually or allow scheduled runs.

Building and Pushing the Airflow Image
docker build -t <registry>/coretelecoms-airflow:latest .
docker push <registry>/coretelecoms-airflow:latest
Update AIRFLOW_IMAGE_NAME in docker-compose.yaml accordingly.

Terraform
	•	AWS: S3 data lake with versioning (resources.tf)
	•	BigQuery: Bronze/Silver/Gold datasets and views (bigquery.tf)
	•	Region defaults:
	•	gcp_region: europe-north1
	•	bq_default_location: EU
Example:
terraform init
terraform plan -var="gcp_project_id=<project>" -var="gcp_region=europe-north1"
terraform apply -auto-approve -var="gcp_project_id=<project>" -var="gcp_region=europe-north1"

dbt (BigQuery Target)
	•	Profiles target the dataset created via Terraform (coretelecoms_raw)
	•	Uses the same service account as Airflow
	•	Models build from Bronze → Silver → Gold
	•	Example marts include fact_complaints

⸻

Credentials Guidance
	•	AWS: Use Airflow connections or IAM roles — never commit keys
	•	Google Sheets: Share your private copy of the sheet with the service account email
	•	Postgres: Store credentials in Airflow connections and rotate regularly

⸻

Next Steps / Hardening
	•	Add Slack/Teams alerting for DAG failures
	•	Add data quality checks (dbt tests or Great Expectations)
	•	Add CI to run DAG tests, linting, and Terraform validation
	•	Move Terraform state to a remote backend (S3 or GCS)
