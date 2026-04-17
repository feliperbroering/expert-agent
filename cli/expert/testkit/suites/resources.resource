*** Settings ***
Documentation     Shared keywords and variables for the expert-agent E2E kit.
...
...               All suites import this resource and rely on the following
...               variables (resolved from environment by default; override on
...               the command line with `robot --variable KEY:value`):
...
...               | Variable                | Env fallback                     |
...               |-------------------------|----------------------------------|
...               | ${ENDPOINT}             | ${EXPERT_AGENT_ENDPOINT}         |
...               | ${API_KEY}              | ${EXPERT_AGENT_API_KEY}          |
...               | ${SCHEMA}               | ${EXPERT_AGENT_SCHEMA}           |
...               | ${SAMPLE_QUESTION}      | ${EXPERT_AGENT_SAMPLE_QUESTION}  |
...               | ${MAX_TTFT_MS}          | ${EXPERT_AGENT_MAX_TTFT_MS}      |
...               | ${MAX_TOTAL_MS}         | ${EXPERT_AGENT_MAX_TOTAL_MS}     |

Library           OperatingSystem
Library           Collections
Library           String
Library           ExpertLibrary.py    endpoint=${ENDPOINT}    api_key=${API_KEY}

*** Variables ***
${ENDPOINT}             %{EXPERT_AGENT_ENDPOINT=}
${API_KEY}              %{EXPERT_AGENT_API_KEY=}
${SCHEMA}               %{EXPERT_AGENT_SCHEMA=agent_schema.yaml}
${SAMPLE_QUESTION}      %{EXPERT_AGENT_SAMPLE_QUESTION=Summarise your knowledge base in one short sentence.}
# Latency budgets. TTFT = time to first streamed token. Defaults are generous
# enough for a cold start on Cloud Run (min_instances=0). Tighten per agent.
${MAX_TTFT_MS}          ${60000}
${MAX_TOTAL_MS}         ${180000}

*** Keywords ***
Require Remote Config
    [Documentation]    Skips the suite when no live endpoint is configured.
    ${has_endpoint}=    Evaluate    bool($ENDPOINT)
    Skip If    not ${has_endpoint}    EXPERT_AGENT_ENDPOINT not set
    ${has_key}=    Evaluate    bool($API_KEY)
    Skip If    not ${has_key}    EXPERT_AGENT_API_KEY not set

Require Schema File
    File Should Exist    ${SCHEMA}    msg=Schema file not found at '${SCHEMA}'. Set EXPERT_AGENT_SCHEMA.

Endpoint Should Be Healthy
    ${result}=    Probe Health Endpoint
    Should Be Equal As Integers    ${result}[status]    200    Health endpoint returned ${result}[status]
