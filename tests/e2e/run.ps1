# Note: This scrupt requires the docker daemon to be running from within WSL

$ErrorActionPreference = 'Stop'

Push-Location $PSScriptRoot

function _Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]] $DockerArguments)

    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed with exit code $LASTEXITCODE"
    }
}

_Docker build -t aoh-test-server ../../
try {
    _Docker network create aoh-test
} catch {
    # Ignore failure if network exists
}

try {
    for ($i = 1; $i -le 6; $i++) {
        if ($i -eq 6) {
            # Test 6 is different, and we only run it from run.sh
            Write-Output '================================'
            Write-Output "Skipping test$i.yml on Windows runner..."
            Write-Output '================================'
            continue
        }

        Write-Output '================================'
        Write-Output "Running test$i.yml..."
        Write-Output '================================'

        _Docker run --rm --network host --detach -h aoh-test-server `
            --name aoh-test-server aoh-test-server
        _Docker cp "$PSScriptRoot/." 'aoh-test-server:/aoh/'
        Start-Sleep -Seconds 1
        irm http://127.0.0.1:8000/run | python3 - test$i.yml

        if ($LASTEXITCODE -ne 0) {
            Write-Output '================================'
            Write-Output "test$i.yml failed."
            Write-Output '================================'
            throw "test$i.yml failed."
        } else {
            Write-Output '================================'
            Write-Output "test$i.yml passed."
            Write-Output '================================'
            Write-Output ''
        }

        _Docker stop aoh-test-server
        Start-Sleep -Seconds 1
    }
} finally {
    try {
        _Docker stop aoh-test-server
    } catch {
        # Ignore failures if server already stopped
    }
}

Write-Output '================================'
Write-Output 'All tests passed.'
Write-Output '================================'
exit 0
