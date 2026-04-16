# Dedicated service account for the Chroma HTTP server.
#
# Needs full object admin on the memory bucket (list + read + write) because
# the FUSE mount maps the ENTIRE `chroma/` directory — a conditional binding
# on a path prefix would break list operations and corrupt the SQLite index.
# Isolation between agents happens at the Chroma *collection* layer instead.

resource "google_service_account" "chroma" {
  project      = var.project_id
  account_id   = "sa-chroma-server"
  display_name = "Service account for the Chroma HTTP Cloud Run service"
}

resource "google_storage_bucket_iam_member" "chroma_memory" {
  bucket = data.terraform_remote_state.platform.outputs.memory_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.chroma.email}"
}

resource "google_project_iam_member" "chroma_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.chroma.email}"
}

resource "google_project_iam_member" "chroma_metrics" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.chroma.email}"
}
