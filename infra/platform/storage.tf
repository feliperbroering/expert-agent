# Three shared buckets consumed by every agent in this project.
#
# - docs     : source-of-truth for `docs/` (versioning on; no lifecycle so we
#              keep the full edit history of reference material).
# - memory   : ChromaDB persistence mounted via GCS FUSE by the chroma stack
#              (versioning on for crash-safety, public access hard-denied).
# - backups  : nightly Chroma snapshots; lifecycle-deleted after
#              var.backup_retention_days (default 30) days.

resource "google_storage_bucket" "docs" {
  name     = "${var.project_id}-docs"
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.storage]
}

resource "google_storage_bucket" "memory" {
  name     = "${var.project_id}-memory"
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.storage]
}

resource "google_storage_bucket" "backups" {
  name     = "${var.project_id}-backups"
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = var.backup_retention_days
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.storage]
}
