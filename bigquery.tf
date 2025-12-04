############################################################
# Sample BigQuery provisioning for warehouse + dbt targets #
############################################################

variable "gcp_project_id" {
  description = "GCP project to host the BigQuery dataset"
  type        = string
}

variable "gcp_region" {
  description = "Region for BigQuery (e.g. europe-north1)"
  type        = string
  default     = "europe-north1"
}

variable "bq_default_location" {
  description = "Location for dataset/tables"
  type        = string
  default     = "EU"
}

locals {
  bq_dataset_id = "coretelecoms_raw"
}

# Dataset that can be referenced by dbt profiles.yml
resource "google_bigquery_dataset" "coretelecoms_raw" {
  dataset_id    = local.bq_dataset_id
  friendly_name = "CoreTelecoms Raw Layer"
  location      = var.bq_default_location
  labels = {
    env = "prod"
  }
}

# Raw table for customers ingested from S3 parquet
resource "google_bigquery_table" "raw_customers" {
  dataset_id = google_bigquery_dataset.coretelecoms_raw.dataset_id
  table_id   = "raw_customers"
  deletion_protection = false
  schema = jsonencode([
    { name = "customer_id", type = "STRING", mode = "REQUIRED" },
    { name = "first_name", type = "STRING", mode = "NULLABLE" },
    { name = "last_name", type = "STRING", mode = "NULLABLE" },
    { name = "email", type = "STRING", mode = "NULLABLE" },
    { name = "phone", type = "STRING", mode = "NULLABLE" },
    { name = "gender", type = "STRING", mode = "NULLABLE" },
    { name = "city", type = "STRING", mode = "NULLABLE" },
    { name = "state", type = "STRING", mode = "NULLABLE" },
    { name = "ingestion_ts", type = "TIMESTAMP", mode = "NULLABLE" },
  ])
}

# Staging table shape for daily complaints (call center, social, web forms)
resource "google_bigquery_table" "stg_complaints" {
  dataset_id = google_bigquery_dataset.coretelecoms_raw.dataset_id
  table_id   = "stg_complaints"
  deletion_protection = false
  schema = jsonencode([
    { name = "source_system", type = "STRING", mode = "REQUIRED" },
    { name = "customer_id", type = "STRING", mode = "REQUIRED" },
    { name = "agent_id", type = "STRING", mode = "NULLABLE" },
    { name = "complaint_type", type = "STRING", mode = "NULLABLE" },
    { name = "platform", type = "STRING", mode = "NULLABLE" },
    { name = "status", type = "STRING", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "resolved_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "duration_seconds", type = "INTEGER", mode = "NULLABLE" },
    { name = "ingestion_ts", type = "TIMESTAMP", mode = "NULLABLE" },
  ])
}

# Example modelled view (dbt can materialize as table if needed)
resource "google_bigquery_table" "fact_complaints" {
  dataset_id = google_bigquery_dataset.coretelecoms_raw.dataset_id
  table_id   = "fact_complaints"
  deletion_protection = false

  view {
    use_legacy_sql = false
    query = <<-SQL
      SELECT
        c.customer_id,
        CONCAT(IFNULL(rc.first_name, ''), ' ', IFNULL(rc.last_name, '')) AS customer_name,
        MIN(c.created_at) AS first_seen,
        COUNT(*) AS complaints_count,
        COUNTIF(LOWER(c.status) = 'resolved') AS resolved_count,
        AVG(c.duration_seconds) AS avg_duration_seconds,
        ARRAY_AGG(DISTINCT c.platform IGNORE NULLS) AS platforms,
        CURRENT_TIMESTAMP() AS refreshed_at
      FROM `${var.gcp_project_id}.${google_bigquery_dataset.coretelecoms_raw.dataset_id}.${google_bigquery_table.stg_complaints.table_id}` c
      LEFT JOIN `${var.gcp_project_id}.${google_bigquery_dataset.coretelecoms_raw.dataset_id}.${google_bigquery_table.raw_customers.table_id}` rc
        ON rc.customer_id = c.customer_id
      GROUP BY 1, 2
    SQL
  }
}

# Output variable useful for dbt profile templating
output "bigquery_dataset" {
  value       = google_bigquery_dataset.coretelecoms_raw.dataset_id
  description = "Dataset id to plug into dbt profiles.yml"
}
