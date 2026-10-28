# JSONPath compatibility ledger

## Wildcard/filter composition for issue #122

Measured on 2026-10-28. Both `$.*[?()]` and `$[*][?()]` now apply the
wildcard first and then filter children of each selected value. The implementation
uses the child traversal and object-member path handling added by PR #123.

The checked-out baseline is `aeaa68237eb862069061d2797de8c0e790c57c11`
(PR #123). Contrary to the older issue report, this revision also combines the
wildcard and filter on objects: `{"b":{"a":1}}` returns `[{"a":1}]` before
this change, and `[]` after it.

### Pinned sources and artifacts

| Baseline | Pin |
| --- | --- |
| ValkeyJSON before | `aeaa68237eb862069061d2797de8c0e790c57c11` |
| cburgmer/json-path-comparison | `e090dae440ac22a5da2a33a74ea65c351124fe97` |
| jsonpath-standard/jsonpath-compliance-test-suite | `20ebdcce5008c8a777ee9c80ad853ecf606950b5` |
| RFC | RFC 9535, sections 2.3.2, 2.3.5, and 2.5.1 |
| RedisJSON release | ReJSON module version `20809` (2.8.9) |
| Redis 8 bundled JSON | ReJSON module version `81000` |
| RedisJSON release image | `redis/redis-stack-server@sha256:798ab84d9f266936b034ab11c4d04a2b8e4b441884c5aa7d17ac951eefdf742a` |
| Redis 8 image | `redis@sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5` |

[Raw outcomes](jsonpath-wildcard-filter-outcomes.json) contain each document,
selector, reply, module hash, and local command transcript location. The before
artifact uses the two selector source files from the pinned revision and the
unchanged module objects from this checkout. The after artifact contains the
working tree change. Each Valkey instance passed the verification helper's doctor
check before use and was stopped after collection. Both Redis containers used
no network interface and were removed after collection.

These RedisJSON measurements use the available pinned images. They do not
measure RedisJSON tip. No source revision is inferred from a module version.

### Value and path expectations

These expectations apply to both wildcard forms followed by `[?(@.a==1)]`.
Paths below use the selector's JSON Pointer representation. Object member names
remain escaped for safe mutation. For example, `/group/a~1b~0c` identifies the
normalized JSONPath `$['group']['a/b~c']`.

| Document | Values before | Values after | Selected path after |
| --- | --- | --- | --- |
| `[{"a":1}]` | `[{"a":1}]` | `[]` | none |
| `{"b":{"a":1}}` | `[{"a":1}]` | `[]` | none |
| `[[{"a":1},{"a":2}]]` | `[]` | `[{"a":1}]` | `/0/0` |
| `{"group":{"a/b~c":{"a":1},"keep":{"a":2}}}` | `[]` | `[{"a":1}]` | `/group/a~1b~0c` |
| `{"group":[{"a":1},{"a":2}]}` | not measured | `[{"a":1}]` | `/group/0` |
| `[{"pick":{"a":1},"keep":{"a":2}}]` | not measured | `[{"a":1}]` | `/0/pick` |
| `[]`, `{}`, `[[],{},1]` | `[]` | `[]` | none |

The focused selector tests assert value and path together. Integration tests
assert reads, numeric updates, sets, deletes, and the full stored document after
mutation. Positive cases cover both an array and an object as the outer
container. No-match cases prove that commands leave the document intact.
External command results provide values only; RedisJSON normalized paths were
not measured separately.

### Separate compatibility deltas

| Comparison | Measured coverage | Before | After | Change |
| --- | --- | --- | --- | --- |
| cburgmer | 2 wildcard/filter queries | 0/2 match | 2/2 match | +2 |
| Official CTS | 3 existing wildcard cases, out of 715 total | 3/3 pass | 3/3 pass | 0 |
| RFC companion cases | 29 value cases and 8 invalid-filter cases | 14/37 pass | 35/37 pass | +21 |
| RedisJSON 2.8.9 | All 42 recorded queries | 19/42 match | 42/42 match | +23 |
| Redis 8 bundled JSON | All 42 recorded queries | 17/42 match | 40/42 match | +23 |

Error comparisons count rejection, not exact error wording. The recursive
cburgmer query has `ALLOW_UNORDERED`; its selected values now agree with the
recorded Rust `serde_json_path` result. The non-recursive query now agrees with
the published `[]` consensus. The pinned CTS has no direct wildcard-then-filter
composition case; the RFC companion cases above are local coverage, not added
upstream CTS passes. No whole-suite CTS improvement is claimed.

No regressions were observed in the measured cases. Two RFC companion cases
still diverge: `$.*[?(@>2)]` and `$[*][?(@>2)]` on `[1,3]` return `[3]` in both
ValkeyJSON and RedisJSON 2.8.9. RFC child-selection semantics and the Redis 8
image return `[]`.
Scalar self-filtering is outside issue #122 and remains unchanged.

The spaced malformed suffixes `$.*[ ?(@.a==1]` and `$[*][ ?(@.a==1]` previously
returned `[]` on empty arrays and objects. They now report syntax errors. The
same malformed suffixes without spaces continue to report errors. This change
validates the following filter before wildcard traversal; it does not introduce
a general syntax-only parser for every possible remaining segment.

Scalar attribute-existence filters, such as `$.*[?(@.a)]`, now return no matches
for scalar values and continue to other wildcard branches. Both pinned Redis
images agree. Bare scalar comparisons retain the behavior described above.

Syntax validation uses a separate selector in READ mode. It retains the real
root for `$` comparisons and uses an empty array for filter candidates. Its
lexer cannot consume the live evaluator's recursive-token budget. A regression
query with 20 matching branches and a `..x` suffix proves this boundary.

### Mutation compatibility

The raw outcome file contains eight command sequences. Each sequence records
`JSON.GET`, `JSON.NUMINCRBY`, `JSON.SET` of a field, `JSON.SET` of the selected
node, `JSON.DEL`, and reads of the full document after mutations.

| Baseline | Full reply sequences that match | Stored-document sequences that match |
| --- | --- | --- |
| RedisJSON 2.8.9 | 0/8 | 2/8 |
| Redis 8 bundled JSON | 6/8 | 8/8 |

All six positive mutation sequences agree with the Redis 8 image. In the two
no-match sequences, ValkeyJSON returns `OK` for both sets. Both Redis images
report `Err wrong static path`. The stored documents agree. This is an existing
ValkeyJSON no-match set reply policy, not a new write target divergence.

RedisJSON 2.8.9 reads the selected object children but does not mutate them in
these six positive sequences. Numeric updates report `ERR Path does not exist`,
sets return nil, and deletion reports zero. This release limitation differs
from the Redis 8 image. The implementation follows the sequentially selected
nodes and the newer baseline's mutation behavior.

### Test coverage

- Five new selector fixtures. They cover 18 value/path cases, 24 invalid-filter
  cases, 8 scalar/mixed attribute cases, 2 rooted comparisons, and 2 recursive
  budget cases.
- Existing object wildcard/filter expectations now use sequential semantics.
- The existing scalar attribute test now expects an empty result.
- 50 new integration cases, including reads and mutations.
- Final full unit suite. 235 passed.
- Final selector suite. 44 passed.
- Final related integration suite. 90 passed.
