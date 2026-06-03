# Valkey JSON

Valkey-json is a Valkey module written in C++ that provides native JSON (JavaScript Object Notation) support for Valkey. The implementation complies with RFC7159 and ECMA-404 JSON data interchange standards. Users can natively store, query, and modify JSON data structures using the JSONPath query language. The query expressions support advanced capabilities including wildcard selections, filter expressions, array slices, union operations, and recursive searches.

Valkey-json leverages [RapidJSON](https://rapidjson.org/), a high-performance JSON parser and generator for C++, chosen for its small footprint and exceptional performance and memory efficiency. As a header-only library with no external dependencies, RapidJSON provides robust Unicode support while maintaining a compact memory profile of just 16 bytes per JSON value on most 32/64-bit machines.

### Building and testing the module
Valkey JSON uses CMake for its build system. To simplify, a build script is provided. 

To build only valkey-json module, use:
```text
./build.sh
```
To build and run unit tests, use:
```text
./build.sh --unit
```
To view the available arguments, use:
```text
./build.sh --help
```

The default valkey version is "unstable" for integration tests. To override it, do:
```text
# Run integration tests with valkey-server (8.1)
SERVER_VERSION=8.1 ./build.sh --integration
```

Custom compiler flags can be passed to the build script via environment variable CFLAGS. For example:
```text
CFLAGS="-O0 -Wno-unused-function" ./build.sh
```

To run single integration test:
```text
TEST_PATTERN=<test-function-or-file> ./build.sh --integration
```
e.g.,
```text
TEST_PATTERN=test_sanity ./build.sh --integration
TEST_PATTERN=test_rdb.py ./build.sh --integration
```

`ASAN_BUILD` works with any of the build script options and enables memory leak
checks in the integration tests.

To build the module with ASAN and run tests
```text
export ASAN_BUILD=true
./build.sh --integration
```
To skip building Valkey from source and reuse an externally built `valkey-server` binary, set `VALKEY_SERVER_PATH` to its absolute path.
The binary will be copied into the integration test directory; `valkeymodule.h` is still fetched from the Valkey repo for compiling the module:
```text
SERVER_VERSION=unstable VALKEY_SERVER_PATH=/path/to/valkey-server ./build.sh --integration
```

## Cleaning
```text
# Clean build artifacts
./build.sh --clean
```

## Load the Module
To load the module on Valkey, use any of the following:

#### Using valkey.conf:
```
1. Add the following to valkey.conf:
    loadmodule /path/to/libjson.so
2. Start valkey-server:
    valkey-server /path/to/valkey.conf
```

#### Starting valkey with --loadmodule option:
```text
valkey-server --loadmodule /path/to/libjson.so
```

#### Using Valkey command MODULE LOAD:
```
1. Connect to a running Valkey instance using valkey-cli
2. Execute Valkey command:
    MODULE LOAD /path/to/libjson.so
```

## Configuration

### Document path limit (`json.max-path-limit`)

JSON documents are subject to a **maximum nesting depth** (path limit). This limit caps how deeply objects and arrays can be nested (e.g. `a.b.c.d...`). It is used to avoid unbounded recursion and stack overflow when parsing, merging, or traversing documents.

- **Config key:** `json.max-path-limit`
- **Default:** 128
- **Range:** 0 to INT_MAX

If an operation would create or load a document whose nesting depth exceeds this limit, the module returns an error: *"Document path nesting limit is exceeded"*. The same limit is enforced when merging values (e.g. with `JSON.MERGE` or merge semantics in `JSON.SET`): once the recursion depth reaches the limit, merging stops and the new value is used as-is for the remainder of the path.

To change the limit (e.g. to 256):

```text
CONFIG SET json.max-path-limit 256
```

### Debug commands (`json.debug-mode`)

The `JSON.DEBUG KEYTABLE-CORRUPT`, `JSON.DEBUG KEYTABLE-CLEAR`, and `JSON.DEBUG KEYTABLE-DISTRIBUTION` subcommands are intended for development and debugging only. They are gated behind the `json.debug-mode` hidden module config, which is **immutable** — it can only be set at module load time.

To enable debug commands, load the module and set the config via Valkey's CLI or config file:

```text
valkey-server --loadmodule /path/to/libjson.so --json.debug-mode yes
```

Or in `valkey.conf`:

```text
loadmodule /path/to/libjson.so
json.debug-mode yes
```

When `debug-mode` is not enabled (the default), these subcommands return an error.

## Supported  Module Commands
```text
JSON.ARRAPPEND
JSON.ARRINDEX
JSON.ARRINSERT
JSON.ARRLEN
JSON.ARRPOP
JSON.ARRTRIM
JSON.CLEAR
JSON.DEBUG
JSON.DEL
JSON.FORGET
JSON.GET
JSON.MGET
JSON.MSET
JSON.NUMINCRBY
JSON.NUMMULTBY
JSON.OBJKEYS
JSON.OBJLEN
JSON.RESP
JSON.SET
JSON.STRAPPEND
JSON.STRLEN
JSON.TOGGLE
JSON.TYPE
```
