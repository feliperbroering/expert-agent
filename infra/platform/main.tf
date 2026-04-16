terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # State is stored in the per-project bootstrap bucket created by
  # scripts/bootstrap-project.sh. Override `bucket` at init time with
  # `-backend-config="bucket=<PROJECT_ID>-tfstate"` for other projects.
  backend "gcs" {
    prefix = "platform"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
