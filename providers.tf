terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.23.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "6.17.0"
    }
  }
}

provider "aws" {
  region = "eu-north-1"
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}
