*** Settings ***
Documentation     Validates that `expert init` scaffolds a working agent project.
...               Offline — exercises the CLI without hitting any backend.
Resource          resources.resource

*** Variables ***
${TMP_AGENT_NAME}    e2e-scaffold
${TMP_ROOT}          %{ROBOT_TEMPDIR=/tmp}/expert-e2e-create

*** Test Cases ***
Scaffold A New Agent Project
    Remove Directory    ${TMP_ROOT}    recursive=True
    Create Directory    ${TMP_ROOT}
    Run Expert CLI    init    ${TMP_AGENT_NAME}    --yes    cwd=${TMP_ROOT}
    Directory Should Exist    ${TMP_ROOT}/${TMP_AGENT_NAME}
    File Should Exist         ${TMP_ROOT}/${TMP_AGENT_NAME}/agent_schema.yaml
    Directory Should Exist    ${TMP_ROOT}/${TMP_AGENT_NAME}/prompts
    Directory Should Exist    ${TMP_ROOT}/${TMP_AGENT_NAME}/docs

Scaffold Validates Out Of The Box
    [Documentation]    A freshly scaffolded schema must pass `expert validate`
    ...                with zero manual edits.
    ${schema}=    Set Variable    ${TMP_ROOT}/${TMP_AGENT_NAME}/agent_schema.yaml
    Run Expert CLI    validate    --schema    ${schema}

Re-Running Init Refuses To Overwrite
    [Documentation]    Protects users from accidentally nuking an existing project.
    Run Expert CLI    init    ${TMP_AGENT_NAME}    --yes    cwd=${TMP_ROOT}    expect_rc=${1}
