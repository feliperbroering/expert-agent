# Chroma HTTP server — single writer, internal-only.
#
# Key design choices:
# - min = max = 1: ChromaDB's on-disk SQLite catalog is NOT safe for
#   concurrent writers. Pinning one instance avoids corruption.
# - INGRESS_TRAFFIC_INTERNAL_ONLY: only Cloud Run services inside the same
#   project/VPC connector can reach it. Agents call it via the run.invoker
#   role granted in the agent stack.
# - GCS FUSE volume mounted at /chroma/chroma (ChromaDB's default persist
#   path when PERSIST_DIRECTORY is set). `only-dir=chroma` scopes the mount
#   to gs://${memory_bucket}/chroma/ so the rest of the bucket stays isolated
#   from the container filesystem.
# - timeout=3600s: long-lived queries / bulk upserts need headroom; Chroma
#   itself is fast but the FUSE layer can stall briefly during SQLite WAL
#   checkpoints.

resource "google_cloud_run_v2_service" "chroma" {
  provider     = google-beta
  project      = var.project_id
  name         = "chroma-server"
  location     = var.region
  ingress      = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  launch_stage = "GA"

  template {
    service_account = google_service_account.chroma.email
    timeout         = "3600s"

    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    containers {
      image = var.chroma_image

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
      }

      ports {
        container_port = 8000
      }

      env {
        name  = "IS_PERSISTENT"
        value = "TRUE"
      }

      env {
        name  = "PERSIST_DIRECTORY"
        value = "/chroma/chroma"
      }

      volume_mounts {
        name       = "chroma-data"
        mount_path = "/chroma/chroma"
      }
    }

    volumes {
      name = "chroma-data"

      gcs {
        bucket    = data.terraform_remote_state.platform.outputs.memory_bucket
        read_only = false
        mount_options = [
          "only-dir=chroma",
          "implicit-dirs",
        ]
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_storage_bucket_iam_member.chroma_memory,
  ]
}
