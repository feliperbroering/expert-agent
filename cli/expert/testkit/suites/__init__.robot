*** Settings ***
Documentation     End-to-end test kit for expert-agent deployments.
...
...               Suites, in dependency order:
...                 01_validate       — offline schema validation (safe on PRs)
...                 02_create         — `expert init` scaffolding
...                 03_update         — round-trip a schema edit
...                 04_deploy         — /health, /ready, auth on a live endpoint
...                 05_ask_latency    — /ask smoke + latency budgets
...                 06_sessions       — LGPD session lifecycle
...
...               Run the whole kit with `expert test`, or cherry-pick via
...               `expert test --suite 05_ask_latency`.

Metadata    Product    expert-agent
Metadata    Kit Version    0.1.0
