cmake_minimum_required(VERSION 3.17)

include(FetchContent)
include(ExternalProject)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Detect the system architecture
EXECUTE_PROCESS(
    COMMAND uname -m
    COMMAND tr -d '\n'
    OUTPUT_VARIABLE ARCHITECTURE
)

if("${ARCHITECTURE}" STREQUAL "x86_64"
   OR "${ARCHITECTURE}" STREQUAL "aarch64"
   OR "${ARCHITECTURE}" STREQUAL "arm64")
    message("Building valkey-json for ${ARCHITECTURE}")
else()
    message(
        FATAL_ERROR
            "Unsupported architecture: ${ARCHITECTURE}. valkey-json is only supported on x86_64, aarch64 and arm64"
    )
endif()

# Project definition
project(ValkeyJSONModule VERSION 1.0.1 LANGUAGES C CXX)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-mismatched-tags -Wno-format")

# Clang related adjustments
set(COMPILER_IS_CLANG OFF)
if (${CMAKE_C_COMPILER_ID} STREQUAL "Clang" OR ${CMAKE_C_COMPILER_ID} STREQUAL "AppleClang")
    set(COMPILER_IS_CLANG ON)
endif()

if (COMPILER_IS_CLANG)
    message(STATUS "Defining VALKEYMODULE_ATTR_COMMON => __attribute__((weak))")
    add_definitions(-DVALKEYMODULE_ATTR_COMMON=__attribute__\(\(weak\)\))
endif()

if(APPLE AND NOT COMPILER_IS_CLANG)
    # Force clang compiler on macOS
    find_program(CLANGPP "clang++")
    find_program(CLANG "clang")
    if(CLANG AND CLANGPP)
          message(STATUS "Found ${CLANGPP}, ${CLANG}")
          set(CMAKE_CXX_COMPILER ${CLANGPP})
          set(CMAKE_C_COMPILER ${CLANG})
    endif()
endif()

# ASAN build option
option(ENABLE_ASAN "Enable Address Sanitizer" OFF)

# ASan flags configuration
if(ENABLE_ASAN)
    message("Building with Address Sanitizer enabled")
    set(ASAN_FLAGS "-fsanitize=address")
endif()

# Set the name of the JSON shared library
set(JSON_MODULE_LIB json)

option(BUILD_RELEASE "Build only valkey-json module" OFF)
option(ENABLE_UNIT_TESTS "Build the module and runs unit tests" ON)
option(ENABLE_INTEGRATION_TESTS "Build the module and runs integration tests" ON)

# Define the Valkey directories used when building from source
set(VALKEY_DOWNLOAD_DIR "${CMAKE_BINARY_DIR}/_deps/valkey-src")
set(VALKEY_BIN_DIR "${CMAKE_BINARY_DIR}/_deps/valkey-src/src/valkey/src")

# Valkey version
if(NOT VALKEY_VERSION)
    set(VALKEY_VERSION unstable)
endif()
message("Valkey version: ${VALKEY_VERSION}")

# Compiler flags that can be overridden in command line
if(NOT CFLAGS)
    # Include debug symbols and set optimize level
    set(CFLAGS "-g -O3 -fno-omit-frame-pointer -Wall -Werror -Wextra")
endif()

# Add ASan flags if enabled
if(ENABLE_ASAN)
    set(CFLAGS "${CFLAGS} ${ASAN_FLAGS}")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} ${ASAN_FLAGS}")
    set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} ${ASAN_FLAGS}")
endif()

# Determine Valkey build command depending on build type
if((BUILD_RELEASE OR ENABLE_UNIT_TESTS) AND NOT ENABLE_INTEGRATION_TESTS)
    set(VALKEY_BUILD_CMD ${CMAKE_COMMAND} -E echo "Skipping build step for release build")
else()
    if(ENABLE_ASAN)
        set(VALKEY_BUILD_CMD make distclean && make -j SANITIZER=address)
    else()
        set(VALKEY_BUILD_CMD make distclean && make -j)
    endif()
endif()

ExternalProject_Add(
    valkey
    GIT_REPOSITORY https://github.com/valkey-io/valkey.git
    GIT_TAG ${VALKEY_VERSION}
    PREFIX ${VALKEY_DOWNLOAD_DIR}
    CONFIGURE_COMMAND ""
    BUILD_COMMAND ${VALKEY_BUILD_CMD}
    INSTALL_COMMAND ""
    BUILD_IN_SOURCE 1
)

# Define the paths for the copied files
set(VALKEY_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/include")
set(VALKEY_BINARY_DEST "${CMAKE_CURRENT_SOURCE_DIR}/tst/integration/.build/binaries/${VALKEY_VERSION}")

ExternalProject_Add_Step(
    valkey
    copy_header_files
    COMMENT "Copying header files to include/ directory"
    DEPENDEES download
    DEPENDERS configure
    COMMAND ${CMAKE_COMMAND} -E make_directory ${VALKEY_INCLUDE_DIR}
    COMMAND ${CMAKE_COMMAND} -E copy ${VALKEY_DOWNLOAD_DIR}/src/valkey/src/valkeymodule.h ${VALKEY_INCLUDE_DIR}/valkeymodule.h
    ALWAYS 1
)

# Integration tests require the valkey-test-framework which is only needed when
# building Valkey from source.
if(ENABLE_INTEGRATION_TESTS)
    # Copy the valkey-server binary after building
    add_custom_command(TARGET valkey
            POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E make_directory ${VALKEY_BINARY_DEST}
            COMMAND ${CMAKE_COMMAND} -E copy ${VALKEY_BIN_DIR}/valkey-server ${VALKEY_BINARY_DEST}/valkey-server
            COMMENT "Copied valkey-server to destination directory"
        )
    # Define valkey-test-framework commit id
    set(VALKEY_TEST_FRAMEWORK_COMMIT "9fb28b74efd122324db00498a2fde6e5d281c90f" CACHE STRING "Valkey-test-framework commit to use")

    # Set the download directory for Valkey-test-framework
    set(VALKEY_TEST_FRAMEWORK_DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/_deps/valkey-test-framework-src")

    ExternalProject_Add(
        valkey-test-framework
        GIT_REPOSITORY https://github.com/valkey-io/valkey-test-framework.git
        GIT_TAG ${VALKEY_TEST_FRAMEWORK_COMMIT}
        GIT_SHALLOW FALSE
        PREFIX "${VALKEY_TEST_FRAMEWORK_DOWNLOAD_DIR}"
        CONFIGURE_COMMAND ""
        BUILD_COMMAND ""
        INSTALL_COMMAND ""
    )

    ExternalProject_Add_Step(
        valkey-test-framework
        copy_pytest_files
        COMMENT "Copying pytest files to tst/integration directory"
        DEPENDEES build
        COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_SOURCE_DIR}/tst/integration
        COMMAND ${CMAKE_COMMAND} -E copy_directory ${VALKEY_TEST_FRAMEWORK_DOWNLOAD_DIR}/src/valkey-test-framework/src ${CMAKE_CURRENT_SOURCE_DIR}/tst/integration/valkeytests
    )
endif()

# Enable instrumentation options if requested
if("$ENV{INSTRUMENT_V2PATH}" STREQUAL "yes")
    add_compile_definitions(INSTRUMENT_V2PATH)
    message("Enabled INSTRUMENT_V2PATH")
endif()

# Disable Doxygen documentation generation
set(BUILD_DOCUMENTATION OFF)
# When CODE_COVERAGE is ON, the package is built twice, once for debug and once for release.
# To fix the problem, disable the code coverage.
set(CODE_COVERAGE OFF)

# Fix for linking error when code coverage is enabled on ARM
if(CODE_COVERAGE AND CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_link_options("--coverage")
endif()

# Set C & C++ standard versions
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED True)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)

# Additional flags for all architectures
set(ADDITIONAL_FLAGS "-fPIC")

# RapidJSON SIMD optimization
if("${ARCHITECTURE}" STREQUAL "x86_64")
    set(ADDITIONAL_FLAGS "${ADDITIONAL_FLAGS} -march=nehalem")
elseif("${ARCHITECTURE}" STREQUAL "aarch64")
    set(ADDITIONAL_FLAGS "${ADDITIONAL_FLAGS} -march=armv8-a")
endif()

set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} ${CFLAGS} ${ADDITIONAL_FLAGS}")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${CFLAGS} ${ADDITIONAL_FLAGS}")
message("CMAKE_C_FLAGS: ${CMAKE_C_FLAGS}")
message("CMAKE_CXX_FLAGS: ${CMAKE_CXX_FLAGS}")

# Fetch RapidJSON
FetchContent_Declare(
    rapidjson
    GIT_REPOSITORY https://github.com/Tencent/rapidjson.git
    GIT_TAG ebd87cb468fb4cb060b37e579718c4a4125416c1
)

# Disable RapidJSON tests and examples
set(RAPIDJSON_BUILD_TESTS OFF CACHE BOOL "Build rapidjson tests" FORCE)
set(RAPIDJSON_BUILD_EXAMPLES OFF CACHE BOOL "Build rapidjson examples" FORCE)
set(RAPIDJSON_BUILD_DOC OFF CACHE BOOL "Build rapidjson documentation" FORCE)

# Make Rapidjson available
FetchContent_MakeAvailable(rapidjson)

add_subdirectory(src)

if(ENABLE_UNIT_TESTS OR ENABLE_INTEGRATION_TESTS)
    add_subdirectory(tst)
endif()

if(ENABLE_INTEGRATION_TESTS)
    message("adding test target")
    add_custom_target(test
        COMMENT "Run valkey-json integration tests"
        USES_TERMINAL
        COMMAND rm -rf ${CMAKE_BINARY_DIR}/tst/integration
        COMMAND mkdir -p ${CMAKE_BINARY_DIR}/tst/integration
        COMMAND cp -rp ${CMAKE_SOURCE_DIR}/tst/integration/. ${CMAKE_BINARY_DIR}/tst/integration/
        COMMAND echo "[TARGET] begin integration tests"
        COMMAND ${CMAKE_SOURCE_DIR}/tst/integration/run.sh "test" ${CMAKE_SOURCE_DIR}
        COMMAND echo "[TARGET] end integration tests")
endif()
