variable "project_id" {
  description = "GCP project ID (must match the platform stack)."
  type        = string
}

variable "region" {
  description = "GCP region (must match the platform stack's region so the FUSE mount stays co-located)."
  type        = string
  default     = "southamerica-east1"
}

variable "chroma_image" {
  description = "Pinned ChromaDB container image. Avoid `latest` in production. Must stay in major/minor sync with `chromadb-client` in pyproject.toml."
  type        = string
  default     = "chromadb/chroma:1.5.8"
}

variable "cpu" {
  description = "vCPU allocated to the Chroma container (string, Cloud Run v2 format: \"1\", \"2\", \"4\")."
  type        = string
  default     = "2"
}

variable "memory" {
  description = "Memory allocated to the Chroma container (e.g. \"2Gi\", \"4Gi\")."
  type        = string
  default     = "4Gi"
}
