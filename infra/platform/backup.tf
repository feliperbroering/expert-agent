# Nightly Chroma backup trigger.
#
# This declares only the Cloud Scheduler job that fires once per day. The
# actual Cloud Run Job that performs the tarball+upload of
# gs://${project}-memory/chroma → gs://${project}-backups/chroma/YYYY-MM-DD/
# is intentionally NOT created here — it belongs in a follow-up commit once
# the backup container image is published to Artifact Registry.
#
# TODO(expert-agent): replace `chroma-backup-placeholder` with the real Cloud
# Run Job name once `infra/chroma/backup_job.tf` (or similar) is authored, and
# wire the job's service account to hold
# roles/storage.objectAdmin on the memory + backups buckets.

resource "google_service_account" "chroma_backup_scheduler" {
  project      = var.project_id
  account_id   = "sa-chroma-backup-scheduler"
  display_name = "Cloud Scheduler invoker for the Chroma nightly backup job"

  depends_on = [google_project_service.iam]
}

resource "google_cloud_scheduler_job" "chroma_backup" {
  project     = var.project_id
  region      = var.region
  name        = "chroma-backup-nightly"
  description = "Nightly trigger for the Chroma backup Cloud Run Job (skeleton — target job not yet deployed)."
  schedule    = "0 3 * * *"
  time_zone   = "Etc/UTC"

  attempt_deadline = "320s"

  retry_config {
    retry_count          = 3
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
  }

  http_target {
    http_method = "POST"
    # TODO(expert-agent): replace `chroma-backup-placeholder` with the actual
    # google_cloud_run_v2_job.chroma_backup.name once the backup job exists.
    uri = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/chroma-backup-placeholder:run"

    oauth_token {
      service_account_email = google_service_account.chroma_backup_scheduler.email
    }
  }

  depends_on = [
    google_project_service.cloudscheduler,
    google_project_service.run,
  ]
}
