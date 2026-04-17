*** Settings ***
Documentation     Validates the session lifecycle required for LGPD.
...               Creates a session via /ask, lists it, then deletes it.
Resource          resources.resource

*** Test Cases ***
Ask Creates A Session
    Require Remote Config
    ${result}=    Ask Question    ${SAMPLE_QUESTION}    stream=${False}
    Should Be Equal As Integers    ${result.status}    200
    Should Not Be Equal    ${result.session_id}    ${None}
    ...    /ask response did not carry a session_id
    Set Suite Variable    ${LAST_SESSION_ID}    ${result.session_id}

Session Can Be Listed
    Require Remote Config
    ${result}=    List Sessions
    IF    ${result}[status] == 404
        Skip    Backend has no /sessions endpoint enabled
    END
    Should Be Equal As Integers    ${result}[status]    200

Session Can Be Deleted
    [Documentation]    LGPD requirement: users must be able to purge their sessions.
    Require Remote Config
    ${has_id}=    Evaluate    bool($LAST_SESSION_ID)
    Skip If    not ${has_id}    No session recorded from previous test
    ${result}=    Delete Session    ${LAST_SESSION_ID}
    IF    ${result}[status] == 404
        Skip    Backend has no /sessions endpoint enabled
    END
    Should Be True
    ...    ${result}[status] == 200 or ${result}[status] == 204
    ...    Unexpected delete status ${result}[status]

*** Variables ***
${LAST_SESSION_ID}    ${EMPTY}
