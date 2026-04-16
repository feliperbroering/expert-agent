# Single Docker repository that hosts both the expert-agent backend image
# and (optionally) a pinned Chroma image. One repo per project keeps IAM
# and pull URLs simple.

resource "google_artifact_registry_repository" "expert_agent" {
  project       = var.project_id
  location      = var.region
  repository_id = "expert-agent"
  format        = "DOCKER"
  description   = "expert-agent backend + chroma container images"

  depends_on = [google_project_service.artifactregistry]
}
