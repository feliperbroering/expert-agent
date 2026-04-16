# Single Firestore database in Native mode, co-located with Cloud Run.
#
# `delete_protection_state = "DELETE_PROTECTION_ENABLED"` avoids accidental
# destruction via `tofu destroy`. Remove manually via console/CLI before
# running destroy when you really mean it.

resource "google_firestore_database" "default" {
  project                 = var.project_id
  name                    = "(default)"
  location_id             = var.region
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_ENABLED"

  depends_on = [google_project_service.firestore]
}

# Enable Firestore TTL on messages subcollections.
#
# TTL is applied at collection-group level — the collection id is `messages`
# regardless of the nested path under `agents/{agent_id}/users/{user_id}/
# sessions/{session_id}/messages`. The application MUST populate each message
# document with `expires_at = created_at + var.firestore_ttl_days`; Firestore
# then purges expired docs within ~24h of the timestamp.
#
# Note: `ttl_config.state` is computed by the API (it flips through
# CREATING → ACTIVE); merely declaring the block enables TTL.
resource "google_firestore_field" "messages_expires_at_ttl" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "messages"
  field      = "expires_at"

  ttl_config {}
}
