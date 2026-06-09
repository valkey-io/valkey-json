#!/bin/bash

set -e

function print_usage() {
cat<<EOF
Usage: build.sh [--release] [--unit] [--integration] [--clean]

    --help | -h               Print this help message and exit.
    --release                 Builds the release configuration.
    --unit                    Builds the unit tests configuration.
    --integration             Builds the integration tests configuration.
    --clean                   Cleans the build artifacts.

Example usage:

    # Build the release configuration,
    ./build.sh --release

    # Cleans the build artifacts,
    ./build.sh --clean

EOF
}

SCRIPT_DIR=$(pwd)
BUILD_DIR="$SCRIPT_DIR/build"
RUN_UNIT=0
RUN_INTEGRATION=0
BUILD_RELEASE=1
CLEAN_BUILD=0

## Parse command line argument
while [[ $# -gt 0 ]]; 
do
    arg="$1"
    case $arg in
        --release)
            BUILD_RELEASE=1
            RUN_UNIT=0
            RUN_INTEGRATION=0
            ;;
        --unit)
            RUN_UNIT=1
            RUN_INTEGRATION=0
            BUILD_RELEASE=0
            ;;
        --integration)
            RUN_UNIT=0
            RUN_INTEGRATION=1
            ;;
        --clean)
            CLEAN_BUILD=1
            RUN_UNIT=0
            RUN_INTEGRATION=0
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            print_usage
            exit 1
            ;;
        esac
    shift
done

if [ $CLEAN_BUILD -eq 1 ]; then
    echo "Cleaning build artifacts..."
    rm -rf "$BUILD_DIR" tst/integration/valkeytests tst/integration/.build src/include 
    rm -rf tst/integration/assets tst/integration/test-data tst/integration/report.html
    echo "Clean completed"
    exit 0
fi

if [ -z "$SERVER_VERSION" ]; then
    echo "SERVER_VERSION environment variable is not set. Defaulting to \"unstable\"."
    export SERVER_VERSION="unstable"
fi

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

CMAKE_FLAGS=""
if [ -n "${ASAN_BUILD}" ]; then
    CMAKE_FLAGS="-DCMAKE_BUILD_TYPE=Debug -DENABLE_ASAN=ON"
else
    CMAKE_FLAGS="-DCMAKE_BUILD_TYPE=Release"
fi

if [ $RUN_UNIT -eq 1 ]; then
    ENABLE_UNIT_TESTS=ON
else
    ENABLE_UNIT_TESTS=OFF
fi

if [ $RUN_INTEGRATION -eq 1 ]; then
    ENABLE_INTEGRATION_TESTS=ON
else
    ENABLE_INTEGRATION_TESTS=OFF
fi

if [ $BUILD_RELEASE -eq 1 ]; then
    ENABLE_BUILD_RELEASE=ON
else
    ENABLE_BUILD_RELEASE=OFF
fi

CMAKE_FLAGS="$CMAKE_FLAGS -DENABLE_UNIT_TESTS=${ENABLE_UNIT_TESTS} -DENABLE_INTEGRATION_TESTS=${ENABLE_INTEGRATION_TESTS} -DBUILD_RELEASE=${ENABLE_BUILD_RELEASE}"

if [ -n "$VALKEY_SERVER_PATH" ]; then
    if [ ! -f "$VALKEY_SERVER_PATH" ]; then
        echo "Error: VALKEY_SERVER_PATH is set but file does not exist: $VALKEY_SERVER_PATH"
        exit 1
    fi
    echo "Using external valkey-server binary: $VALKEY_SERVER_PATH"
    CMAKE_FLAGS="$CMAKE_FLAGS -DVALKEY_SERVER_PATH=$VALKEY_SERVER_PATH"
fi

if [ -n "$VALKEY_MODULE_H_PATH" ]; then
    if [ ! -f "$VALKEY_MODULE_H_PATH" ]; then
        echo "Error: VALKEY_MODULE_H_PATH is set but file does not exist: $VALKEY_MODULE_H_PATH"
        exit 1
    fi
    echo "Using external valkeymodule.h: $VALKEY_MODULE_H_PATH"
    CMAKE_FLAGS="$CMAKE_FLAGS -DVALKEY_MODULE_H_PATH=$VALKEY_MODULE_H_PATH"
fi

if [ -z "${CFLAGS}" ]; then
    cmake .. -DVALKEY_VERSION=${SERVER_VERSION} ${CMAKE_FLAGS}
else
    cmake .. -DVALKEY_VERSION=${SERVER_VERSION} -DCFLAGS="${CFLAGS}" ${CMAKE_FLAGS}
fi

if [ $BUILD_RELEASE -eq 1 ] && [ $RUN_UNIT -eq 0 ] && [ $RUN_INTEGRATION -eq 0 ]; then
    make -j
    echo "Release build completed"
    exit 0
elif [ $RUN_UNIT -eq 1 ]; then
    echo "Building valkey-json and running unit tests..."
    make -j unit
fi

if [ $RUN_INTEGRATION -eq 1 ]; then
    make -j
    cd "$SCRIPT_DIR"
    REQUIREMENTS_FILE="requirements.txt"
    if command -v pip > /dev/null 2>&1; then
        pip install -r "$SCRIPT_DIR/$REQUIREMENTS_FILE"
    elif command -v pip3 > /dev/null 2>&1; then
        pip3 install -r "$SCRIPT_DIR/$REQUIREMENTS_FILE"
    else
        echo "Error: Neither pip nor pip3 is available."
        exit 1
    fi
    export MODULE_PATH="$BUILD_DIR/src/libjson.so"
    cd "$BUILD_DIR"
    echo "Running integration tests...${TEST_PATTERN}"
    TEST_PATTERN=${TEST_PATTERN} make -j test
fi

echo "Build script completed"
