# Per-agent service account + least-privilege bindings.
#
# Multi-tenant isolation strategy:
# - GCS: conditional IAM that scopes objectAdmin to objects under the
#        `${agent_id}/` prefix of each shared bucket.
# - Firestore: no condition — the app enforces the `agents/${agent_id}/*`
#              path prefix in code (Firestore IAM doesn't support object-
#              level conditions today).
# - Secrets: bindings on the exact per-agent secret + the shared gemini key.
# - Chroma: run.invoker on the chroma-server Cloud Run service only.

resource "google_service_account" "agent" {
  project      = var.project_id
  account_id   = "sa-agent-${var.agent_id}"
  display_name = "expert-agent runtime SA for agent '${var.agent_id}'"
}

# --- GCS: docs bucket (scoped to this agent's prefix) ---

resource "google_storage_bucket_iam_member" "agent_docs" {
  bucket = data.terraform_remote_state.platform.outputs.docs_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent.email}"

  condition {
    title       = "only-own-prefix"
    description = "Restrict access to gs://DOCS_BUCKET/${var.agent_id}/*"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${data.terraform_remote_state.platform.outputs.docs_bucket}/objects/${var.agent_id}/\")"
  }
}

# --- GCS: backups bucket (scoped to this agent's prefix) ---

resource "google_storage_bucket_iam_member" "agent_backups" {
  bucket = data.terraform_remote_state.platform.outputs.backups_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent.email}"

  condition {
    title       = "only-own-prefix"
    description = "Restrict access to gs://BACKUPS_BUCKET/${var.agent_id}/*"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${data.terraform_remote_state.platform.outputs.backups_bucket}/objects/${var.agent_id}/\")"
  }
}

# --- Firestore ---

resource "google_project_iam_member" "agent_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

# --- Secrets ---

resource "google_secret_manager_secret_iam_member" "agent_admin_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.admin_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_secret_manager_secret_iam_member" "agent_gemini_key" {
  project   = var.project_id
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

# --- Chroma: allow this agent to invoke the Chroma Cloud Run service ---

resource "google_cloud_run_v2_service_iam_member" "agent_invokes_chroma" {
  project  = var.project_id
  location = var.region
  name     = data.terraform_remote_state.chroma.outputs.chroma_service_name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.agent.email}"
}

# --- Observability ---

resource "google_project_iam_member" "agent_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_project_iam_member" "agent_metrics" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.agent.email}"
}
