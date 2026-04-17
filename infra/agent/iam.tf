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

# --- GCS: docs + backups buckets ---
#
# Conditional IAM at the object prefix level cannot cover `storage.objects.list`
# because that permission is bucket-scoped (the resource path does NOT include
# `/objects/<prefix>/...`). A condition like `startsWith(".../objects/<id>/")`
# therefore blocks list requests entirely, which breaks the schema bootstrap
# (`list_blobs(prefix=...)` at startup) and the DocsSyncService manifest walk.
#
# Trade-off: we grant unconditional objectAdmin on the shared buckets and
# enforce per-agent prefix discipline in the application layer. Cross-agent
# reads are possible if an agent misuses the client, so each agent SA is
# separate (blast radius = one agent) and audit logs are enabled at the project
# level. Revisit with `storage.objectListPrefix` API attribute when it ships
# with a stable IAM condition helper.
resource "google_storage_bucket_iam_member" "agent_docs" {
  bucket = data.terraform_remote_state.platform.outputs.docs_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_storage_bucket_iam_member" "agent_backups" {
  bucket = data.terraform_remote_state.platform.outputs.backups_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent.email}"
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
#
# Chroma is reachable ONLY from the project's VPC (ingress=INTERNAL_ONLY) and
# the chroma stack grants `allUsers` run.invoker because there's no practical
# way to rotate ID tokens inside Chroma's HTTP client. The agent still needs
# VPC egress (configured in cloud_run.tf) for the call to succeed.

# --- Ingress: allow public HTTPS invocation ---
#
# The Cloud Run IAM layer would otherwise steal the `Authorization: Bearer`
# header (Cloud Run expects an ID token there) and collide with the app's
# own bearer-token scheme (admin key + user key). Making the service
# publicly invokable lets the app be the single source of truth for auth;
# defense-in-depth comes from HTTPS, the app's constant-time key check,
# and slowapi rate limits.
resource "google_cloud_run_v2_service_iam_member" "agent_public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent.name
  role     = "roles/run.invoker"
  member   = "allUsers"
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
