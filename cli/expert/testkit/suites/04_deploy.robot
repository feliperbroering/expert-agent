*** Settings ***
Documentation     Post-deploy health checks. Requires a live endpoint
...               (set EXPERT_AGENT_ENDPOINT + EXPERT_AGENT_API_KEY).
Resource          resources.resource

*** Test Cases ***
Health Endpoint Responds
    Require Remote Config
    ${result}=    Probe Health Endpoint
    Should Be Equal As Integers    ${result}[status]    200

Ready Endpoint Responds
    [Documentation]    After cache warm-up the /ready endpoint should flip to 200.
    ...                Allows a 90s grace window for the first startup.
    Require Remote Config
    Wait Until Keyword Succeeds    90s    5s    Endpoint Should Be Healthy

Unauthenticated Calls Are Rejected
    Require Remote Config
    ${result}=    Ask Question Unauthenticated    ping
    Should Be Equal As Integers    ${result}[status]    401
