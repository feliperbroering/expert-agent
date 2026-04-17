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

# Allow unauthenticated invocations at the IAM layer — security comes from
# `ingress = INGRESS_TRAFFIC_INTERNAL_ONLY`, which only accepts traffic from
# inside the project's VPC (agents reach it via Direct VPC egress). Without
# this binding the agent would need to inject fresh ID tokens on every call
# (Chroma's HTTP client has no native hook for dynamic auth headers).
resource "google_cloud_run_v2_service_iam_member" "chroma_public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.chroma.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
