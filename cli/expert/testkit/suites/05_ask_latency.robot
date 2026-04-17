*** Settings ***
Documentation     Golden-path `/ask` smoke test with latency budgets.
...               Generates pass/fail signal for cold-start regressions,
...               Context Cache misses, and grounding breakages.
Resource          resources.resource

*** Test Cases ***
Warmup Request Completes
    [Documentation]    First request may trigger a cache re-create. We allow
    ...                up to 3× the steady-state budget to soak that up.
    Require Remote Config
    ${budget}=    Evaluate    int($MAX_TOTAL_MS) * 3
    ${result}=    Ask Question    ${SAMPLE_QUESTION}    stream=${False}
    Should Be Equal As Integers    ${result.status}    200
    Should Be True    ${result.elapsed_ms} < ${budget}
    ...    Warmup took ${result.elapsed_ms}ms (budget ${budget}ms)

Steady-State Answer Stays Under Budget
    [Documentation]    Second request hits the warm Context Cache and must
    ...                land well inside ${MAX_TOTAL_MS}ms.
    Require Remote Config
    ${result}=    Ask Question    ${SAMPLE_QUESTION}    stream=${False}
    Should Be Equal As Integers    ${result.status}    200
    Should Be True    ${result.elapsed_ms} < ${MAX_TOTAL_MS}
    ...    Answer took ${result.elapsed_ms}ms (budget ${MAX_TOTAL_MS}ms)
    Log    total_ms=${result.elapsed_ms}

Streaming Answer First Token Under Budget
    [Documentation]    Time-to-first-token is the metric users feel.
    Require Remote Config
    ${result}=    Ask Question    ${SAMPLE_QUESTION}    stream=${True}
    Should Be Equal As Integers    ${result.status}    200
    Should Not Be Equal    ${result.ttft_ms}    ${None}
    ...    No 'token' SSE events received
    Should Be True    ${result.ttft_ms} < ${MAX_TTFT_MS}
    ...    TTFT ${result.ttft_ms}ms (budget ${MAX_TTFT_MS}ms)
    Log    ttft_ms=${result.ttft_ms} total_ms=${result.elapsed_ms}

Answer Contains Non-Empty Text
    Require Remote Config
    ${result}=    Ask Question    ${SAMPLE_QUESTION}    stream=${False}
    ${text}=      Evaluate    $result.body.get('text', '')
    Should Not Be Empty    ${text}
    ${len}=       Get Length    ${text}
    Should Be True    ${len} > 10    Suspiciously short answer: '${text}'

Cache Hit Is Observable
    [Documentation]    Gemini Context Cache must report cached_tokens>0 after
    ...                the first warmup round-trip. Soft assertion — the field
    ...                is optional in the backend response.
    Require Remote Config
    ${result}=    Ask Question    ${SAMPLE_QUESTION}    stream=${False}
    ${usage}=     Evaluate    $result.body.get('usage') if isinstance($result.body, dict) else None
    IF    $usage is None
        Log    Backend did not expose 'usage' — skipping cache-hit assertion    WARN
    ELSE
        ${cached}=    Evaluate    $usage.get('cached_tokens', 0)
        Should Be True    ${cached} > 0
        ...    Expected cached_tokens>0 but got ${cached}
    END
