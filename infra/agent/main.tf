terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # `prefix` is intentionally left blank here and MUST be passed at init
  # time so every agent gets its own state file, e.g.:
  #   tofu init -backend-config="bucket=<PROJECT_ID>-tfstate" \
  #             -backend-config="prefix=agent/ecg-expert"
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Outputs from the platform stack: bucket names, firestore db, registry URL.
data "terraform_remote_state" "platform" {
  backend = "gcs"
  config = {
    bucket = "${var.project_id}-tfstate"
    prefix = "platform"
  }
}

# Outputs from the chroma stack: chroma_url, service name, SA email.
data "terraform_remote_state" "chroma" {
  backend = "gcs"
  config = {
    bucket = "${var.project_id}-tfstate"
    prefix = "chroma"
  }
}

# The shared Gemini API key secret — created ONCE per project by the
# bootstrap script (or manually). Every agent service account gets read
# access to it via the binding in iam.tf.
data "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project_id
  secret_id = "gemini-api-key"
}
