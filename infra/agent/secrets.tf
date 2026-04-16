# Per-agent admin API key secret.
#
# The SECRET RESOURCE is created by tofu; the SECRET VALUE (first version)
# must be added manually after the first apply:
#
#   echo -n 'YOUR_GENERATED_KEY' | gcloud secrets versions add \
#     admin-key-${AGENT_ID} --data-file=- --project=${PROJECT_ID}
#
# Rotate by adding a new version and letting Cloud Run pick up :latest.
#
# The shared `gemini-api-key` secret is NOT created here — it's a
# project-wide singleton referenced via data source in main.tf.

resource "google_secret_manager_secret" "admin_key" {
  project   = var.project_id
  secret_id = local.admin_key_secret_name

  replication {
    auto {}
  }

  labels = {
    agent = var.agent_id
  }

  lifecycle {
    # The secret VALUE (via google_secret_manager_secret_version) is managed
    # out-of-band. If we ever start managing versions here we'd ignore
    # changes on secret_data to avoid overwriting rotations.
    prevent_destroy = false
  }
}
