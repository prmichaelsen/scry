# Conformance bump procedure

When scry-spec advances to a new version, `test_pinned_version_matches_installed`
fails because `PINNED_SCRY_SPEC_VERSION` lags `scry.domain.markers.SCRY_SPEC_VERSION`.

## When to bump

Bump when scry-mcp implements features from a new scry-spec release:
new BASELINE_KINDs, new predicates, new status values, new required
fields, or new behavior specified in the new version.

## Bump procedure

1. Update `src/scry/domain/markers.py::SCRY_SPEC_VERSION` to the new
   scry-spec version string (e.g. `"1.3.0"`).

2. For each new BASELINE_KIND (e.g. `goal` in v1.2.0):
   - Add the kind to `tests/conformance/baseline_kinds.txt`.
   - Create `tests/conformance/fixtures/kinds/<kind>.md` with a minimal
     `@scry.entry` marker using that `kind:`.
     Use a unique fixture ID: `<kind>.conformance-kind~<8hexchars>`.

3. For each new predicate (e.g. `satisfies` in v1.2.0):
   - Add the predicate to `tests/conformance/predicates.txt`.
   - Create `tests/conformance/fixtures/predicates/<predicate>.md` with a
     `@scry.entry` marker that uses that predicate in its relationship fields.
     The referenced target ID does not need to exist in a live DB.
   - **Parser lag note:** if the predicate is in scry-spec but not yet
     exposed by the installed scry-parse version, the fixture file can be
     created but leave the predicate commented out in `predicates.txt` until
     scry-parse ships support. See the `# satisfies` comment in
     `predicates.txt` as the current example of this pattern.

4. For each new status value:
   - Add to `tests/conformance/statuses.txt`.
   - Create `tests/conformance/fixtures/statuses/<status>.md`.

5. For each new required field:
   - Add to `tests/conformance/required_fields.txt`.
   - Create `tests/conformance/fixtures/fields/<field>.md`.

6. Update `tests/conformance/PINNED_SCRY_SPEC_VERSION` to the new version.

7. Run `pytest tests/test_conformance.py -v` to verify all three tests pass.

8. Open a PR with the title prefix `conformance:` so it's grep-able.
   Example: `conformance: bump pin to scry-spec v1.3.0`.

## Invariant

`PINNED_SCRY_SPEC_VERSION` == `SCRY_SPEC_VERSION` == the scry-spec
version scry-mcp currently implements. The three files must always
agree atomically in a single PR.
