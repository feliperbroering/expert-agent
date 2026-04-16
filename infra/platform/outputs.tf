output "project_id" {
  description = "GCP project ID this stack was applied to."
  value       = var.project_id
}

output "region" {
  description = "Region used for regional resources."
  value       = var.region
}

output "docs_bucket" {
  description = "Bucket that stores every agent's reference documents (prefixed by agent_id)."
  value       = google_storage_bucket.docs.name
}

output "memory_bucket" {
  description = "Bucket that backs the Chroma HTTP server's persistent volume via GCS FUSE."
  value       = google_storage_bucket.memory.name
}

output "backups_bucket" {
  description = "Bucket for nightly Chroma snapshots (lifecycle-deleted)."
  value       = google_storage_bucket.backups.name
}

output "firestore_database" {
  description = "Firestore database name (always `(default)` for the single-DB model)."
  value       = google_firestore_database.default.name
}

output "artifact_registry_url" {
  description = "Base URL for pushing/pulling container images (format: REGION-docker.pkg.dev/PROJECT/expert-agent)."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.expert_agent.repository_id}"
}
