#!/usr/bin/env bash

# If environment variable SERVER_VERSION is not set, default to "unstable"
if [ -z "$SERVER_VERSION" ]; then
    echo "SERVER_VERSION environment variable is not set. Defaulting to \"unstable\"."
    export SERVER_VERSION="unstable"
fi

# cd to the current directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "${DIR}"

export SOURCE_DIR=$2
export MODULE_PATH=${SOURCE_DIR}/build/src/libjson.so
echo "Running integration tests against Valkey version $SERVER_VERSION"

if [[ ! -z "${TEST_PATTERN}" ]] ; then
    export TEST_PATTERN="-k ${TEST_PATTERN}"
fi

BINARY_PATH=".build/binaries/${SERVER_VERSION}/valkey-server"

if [[ ! -f "${BINARY_PATH}" ]] ; then
    echo "${BINARY_PATH} missing"
    exit 1
fi

if [[ $1 == "test" ]] ; then
    if [ ! -z "${ASAN_BUILD}" ]; then
        echo "Running tests with AddressSanitizer enabled"

        # Make ASAN/LSAN report reliably. Reports go to stderr detect_leaks=1 enables 
        # leak checks at process exit. We do not abort the process so pytest can finish;
        # any error is caught via the log scan and the pytest exit code below.
        export ASAN_OPTIONS="detect_leaks=1:halt_on_error=0:abort_on_error=0:log_path=stderr${ASAN_OPTIONS:+:${ASAN_OPTIONS}}"

        # Propagate the real pytest exit status through the pipe to tee.
        set -o pipefail
        python -m pytest --capture=sys --html=report.html --cache-clear -v ${TEST_FLAG} ./ ${TEST_PATTERN} 2>&1 | tee test_output.tmp
        PYTEST_STATUS=${PIPESTATUS[0]}
        set +o pipefail

        RED='\033[0;31m'
        NC='\033[0m'
        FAILED=0

        # 1) Any AddressSanitizer error: heap-buffer-overflow, heap-use-after-free,
        #    stack/global-buffer-overflow, etc.
        if grep -Eq "(ERROR|WARNING): AddressSanitizer:|SUMMARY: AddressSanitizer:" test_output.tmp; then
            echo -e "${RED}AddressSanitizer reported errors:${NC}"
            grep -nE "(ERROR|WARNING): AddressSanitizer:|SUMMARY: AddressSanitizer:" test_output.tmp | \
            while read -r line; do
                echo "::error::ASAN: ${line}"
            done
            FAILED=1
        fi

        # 2) Memory leaks reported by LeakSanitizer.
        if grep -q "LeakSanitizer: detected memory leaks" test_output.tmp; then
            echo -e "${RED}Memory leaks detected in the following tests:${NC}"
            LEAKING_TESTS=$(grep -B 2 "LeakSanitizer: detected memory leaks" test_output.tmp | \
                            grep -v "LeakSanitizer" | \
                            grep ".*\.py::")

            LEAK_COUNT=$(echo "$LEAKING_TESTS" | grep -c .)

            # Output each leaking test
            echo "$LEAKING_TESTS" | while read -r line; do
                [ -n "$line" ] && echo "::error::Test with leak: ${line}"
            done

            echo -e "\n${LEAK_COUNT} python integration tests have leaks detected in them"
            FAILED=1
        fi

        # 3) pytest itself failed (assertion failure, or a server crash caused by a
        #    fatal ASAN error that terminated the process mid-test).
        if [ "${PYTEST_STATUS}" -ne 0 ]; then
            echo -e "${RED}pytest exited with status ${PYTEST_STATUS}${NC}"
            echo "::error::pytest exited with status ${PYTEST_STATUS}"
            FAILED=1
        fi

        rm -f test_output.tmp
        if [ "${FAILED}" -ne 0 ]; then
            exit 1
        fi
    else
        python -m pytest --html=report.html --cache-clear -v ${TEST_FLAG} ./ ${TEST_PATTERN}
    fi
else
    echo "Unknown target: $1"
    exit 1
fi

