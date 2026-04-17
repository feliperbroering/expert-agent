# `expert-agent` OpenTofu Infrastructure

Three independent OpenTofu stacks that together provision every Google Cloud
resource an `expert-agent` deployment needs:

```
infra/
├── platform/   # stack 1 — one apply per GCP project  (APIs, buckets, Firestore, Artifact Registry)
├── chroma/     # stack 2 — one apply per GCP project  (Chroma HTTP server on Cloud Run)
└── agent/      # stack 3 — one apply per agent        (Cloud Run + SA + conditional IAM + secrets)
```

State is stored in a per-project GCS bucket `<PROJECT_ID>-tfstate` (created by
`scripts/bootstrap-project.sh`). Each stack uses a distinct `prefix/` inside
that bucket so they evolve independently.

---

## Apply order

```
platform  →  chroma  →  agent (per agent)
```

Destroy order is the reverse. Never destroy `platform` while any agent or the
chroma service still exists — IAM references to the shared buckets will hang.

---

## Bootstrapping a brand-new GCP project

```bash
# 0. Pick the project
PROJECT_ID=my-agents-prod
REGION=us-central1

# 1. One-time imperative bootstrap (APIs + tfstate bucket + registry + firestore)
./scripts/bootstrap-project.sh "$PROJECT_ID" "$REGION"

# 2. Shared Gemini API key (one per project, referenced by every agent)
echo -n 'YOUR_GEMINI_KEY' | \
  gcloud secrets create gemini-api-key --data-file=- --project="$PROJECT_ID"

# 3. Platform stack
cd infra/platform
tofu init -backend-config="bucket=${PROJECT_ID}-tfstate"
tofu apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}"
cd ../..

# 4. Chroma stack
cd infra/chroma
tofu init -backend-config="bucket=${PROJECT_ID}-tfstate"
tofu apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}"
cd ../..
```

After these three steps the project is ready to host agents.

---

## Adding a new agent

One directory, one apply — but **initialise the backend with a unique prefix**
so each agent gets its own state file:

```bash
AGENT_ID=my-expert
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/expert-agent/backend:v0.1.0"

cd infra/agent
tofu init \
  -backend-config="bucket=${PROJECT_ID}-tfstate" \
  -backend-config="prefix=agent/${AGENT_ID}"

tofu apply \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="agent_id=${AGENT_ID}" \
  -var="image=${IMAGE}"
```

**Post-apply manual step** (once per agent): seed the admin API key secret
value. The tofu resource only creates the empty secret container.

```bash
ADMIN_KEY=$(openssl rand -hex 32)
echo -n "$ADMIN_KEY" | \
  gcloud secrets versions add "admin-key-${AGENT_ID}" \
    --data-file=- --project="${PROJECT_ID}"
```

Switching between agents on the same workstation is a matter of
re-running `tofu init -reconfigure -backend-config="prefix=agent/OTHER_ID"`.

---

## Destroy

Reverse order — and remember to disable Firestore delete-protection first if
you really mean to nuke the DB.

```bash
# Per agent
cd infra/agent
tofu init -backend-config="bucket=${PROJECT_ID}-tfstate" \
          -backend-config="prefix=agent/${AGENT_ID}"
tofu destroy -var="project_id=${PROJECT_ID}" -var="agent_id=${AGENT_ID}" \
             -var="image=${IMAGE}"

# Then chroma
cd ../chroma
tofu destroy -var="project_id=${PROJECT_ID}"

# Finally platform — will refuse if Firestore delete-protection is still on.
cd ../platform
tofu destroy -var="project_id=${PROJECT_ID}"
```

---

## Cost expectations (rough, `southamerica-east1`, April 2026)

| Component                       | Idle cost      | Notes                                                   |
|---------------------------------|----------------|---------------------------------------------------------|
| Chroma Cloud Run (min=max=1)    | **~$40/mo**    | Always-on, 2 vCPU / 4 GiB. Single instance per project. |
| Agent Cloud Run (min=0)         | **~$0**        | Scales to zero when idle. Pay only on request.          |
| Firestore (default DB, low QPS) | **~$0**        | Free tier covers most dev traffic.                      |
| GCS (docs + memory + backups)   | **~$0.02/GiB** | Regional storage, egress is the main variable.          |
| Artifact Registry               | **~$0.10/GiB** | Docker image storage.                                   |
| Cloud Scheduler (1 nightly job) | **~$0.10/mo**  | Per-job price.                                          |

The Chroma server dominates idle cost. Share it across every agent in the
project (collection-per-agent isolation) to amortise.

---

## Layout & conventions

- **One file per concern** inside each stack (`apis.tf`, `storage.tf`, …).
- **No provisioners / local-exec** — everything is declarative.
- **Every hardcoded string is a variable** — no project-specific literals.
- **Post-apply manual steps are always documented** next to the resource
  (search for `TODO(expert-agent):` in the `.tf` files).
