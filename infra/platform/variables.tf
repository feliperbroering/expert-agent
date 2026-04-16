variable "project_id" {
  description = "GCP project ID that hosts the expert-agent platform."
  type        = string
}

variable "region" {
  description = "GCP region for regional resources (Cloud Run, buckets, Firestore, Artifact Registry)."
  type        = string
  default     = "southamerica-east1"
}

variable "firestore_ttl_days" {
  description = "Retention in days for per-session chat messages (used by the app when populating `expires_at`)."
  type        = number
  default     = 365
}

variable "backup_retention_days" {
  description = "Lifecycle deletion age (days) for nightly Chroma backup objects in the backups bucket."
  type        = number
  default     = 30
}
