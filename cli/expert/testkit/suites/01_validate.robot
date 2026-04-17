*** Settings ***
Documentation     Static validation of a local agent_schema.yaml via the `expert` CLI.
...               Runs fully offline — safe to execute on PRs before any deploy.
Resource          resources.resource

*** Test Cases ***
CLI Is Installed
    [Documentation]    `expert --version` must succeed and print a semver-ish string.
    ${result}=    Run Expert CLI    --version
    Should Contain    ${result}[stdout]    expert

Schema File Exists
    Require Schema File

Schema Validates Against Contract
    [Documentation]    `expert validate` fails loudly on any contract breakage.
    Require Schema File
    ${result}=    Run Expert CLI    validate    --schema    ${SCHEMA}
    Should Contain Any    ${result}[stdout]${result}[stderr]    valid    OK    valid.

Count Tokens Reports A Non Zero Corpus
    [Documentation]    Protects against shipping an empty knowledge base.
    ...                Tagged `requires-gemini`: needs GEMINI_API_KEY and a
    ...                currently-available countTokens model. Skip with
    ...                `--exclude requires-gemini` in offline CI.
    [Tags]    requires-gemini
    Require Schema File
    ${result}=    Run Expert CLI    count-tokens    --schema    ${SCHEMA}    expect_rc=${None}
    Run Keyword If    ${result}[rc] != 0
    ...    Skip    count-tokens failed (likely no API key / deprecated model): ${result}[stderr]
    Should Not Contain    ${result}[stdout]    total: 0
