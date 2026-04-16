terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    # `google-beta` is required only for the GCS FUSE `mount_options` field
    # on google_cloud_run_v2_service.volumes.gcs — still in beta in 6.x
    # (promoted to GA in hashicorp/google 7.x). All other resources use the
    # stable `google` provider.
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }

  backend "gcs" {
    prefix = "chroma"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Read the platform stack's outputs (bucket names, registry URL, etc.).
# Override `bucket` at init time if your tfstate bucket follows a different
# naming convention:
#   tofu init -backend-config="bucket=<PROJECT_ID>-tfstate"
data "terraform_remote_state" "platform" {
  backend = "gcs"
  config = {
    bucket = "${var.project_id}-tfstate"
    prefix = "platform"
  }
}
