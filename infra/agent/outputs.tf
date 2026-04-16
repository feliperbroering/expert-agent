output "service_url" {
  description = "Public HTTPS URL of the agent Cloud Run service."
  value       = google_cloud_run_v2_service.agent.uri
}

output "service_account_email" {
  description = "Runtime service account email for this agent."
  value       = google_service_account.agent.email
}

output "admin_key_secret_name" {
  description = "Secret Manager secret holding this agent's ADMIN_KEY (value must be set manually)."
  value       = google_secret_manager_secret.admin_key.secret_id
}
