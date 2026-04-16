output "chroma_url" {
  description = "Fully-qualified HTTPS URL of the Chroma server (e.g. https://chroma-server-xxx.run.app)."
  value       = google_cloud_run_v2_service.chroma.uri
}

output "chroma_service_name" {
  description = "Cloud Run service name — used by the agent stack to grant roles/run.invoker."
  value       = google_cloud_run_v2_service.chroma.name
}

output "chroma_service_account_email" {
  description = "Service account email running the Chroma container."
  value       = google_service_account.chroma.email
}
