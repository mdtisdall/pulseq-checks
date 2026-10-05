# Plan: the Pulseq file signature in the result matrix

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: approved (2026-10-05). The user approved the decisions D1 to D6 of
section 5 on 2026-10-05.

## 1. Goal

`ResultMatrix` records the signature of the sequence that the run checked:
the type and the hash of the `[SIGNATURE]` section, as pypulseq read them,
or "no signature". `to_json` writes it and `from_json` reads it.

The reason: pulseq-reports shows a result matrix next to the cards of one
`.seq` file. A caller can give a matrix from an earlier run
(`pulseq-report --check-results FILE.json`, or
`build_cards(seq, check_results=matrix)`). pulseq-reports can compare the
target names, but it cannot find a matrix of a different file. With the
signature in the matrix, pulseq-reports can compare it with
`seq.signature_value` of the file that it reads, and refuse a matrix of a
different file. pulseq-reports does that work, not this plan.

Not in this plan: the verification of the hash (D2), a change of a
`spec.version`, a new JSON format number, and the signature in the summary
of the command `pulseq-check`.

## 2. Context (verified on 2026-10-05, `main` at `100c3bc`, pypulseq fork `a74ab06`)

### 2.1 The signature in pypulseq

1. Pulseq 1.4 and later can end with a `[SIGNATURE]` section:

   ```
   [SIGNATURE]
   # This is the hash of the Pulseq file, calculated right before the [SIGNATURE] section was added
   # ...
   Type md5
   Hash 872c61d6f7c98c964ee2089bf208084e
   ```

   The hash is the MD5 of the file text before `\n[SIGNATURE]`.
2. `seq.write(path)` (`create_signature=True` is the default) writes the
   section. `seq.write(path, create_signature=False)`, and a file older than
   1.4, give a file without it.
3. `seq.read(path)` (`read_seq.py:94–100`) stores `Type` in
   `seq.signature_type`, `Hash` in `seq.signature_value`, and `"Text"` in
   `seq.signature_file`. A new `pp.Sequence()` has `""` in each, and a read
   of a file without a signature does not change them.
4. pypulseq does not verify the hash when it reads a file.
5. `seq.write(...)` with a signature also sets the three attributes on the
   object (`sequence.py:1802–1805`): `"md5"`, the hash of the written file,
   and `"text"`. Thus a `Sequence` object that was written has the signature
   of the written file. An object that was read and then changed keeps the
   signature of the file that it was read from.
6. **A hash that looks like a number.** The `[SIGNATURE]` branch reads the
   section with `__read_definitions`, the reader of `[DEFINITIONS]`, which
   converts each value that `float()` accepts to a `numpy.float64`. About 1
   in 850,000 MD5 hex digests are valid floats: 32 decimal digits, or
   decimal digits with one `e` inside. For such a file,
   `seq.signature_value` is a float (rounded, or `inf`), and the hash text
   is lost. Verified with a real signature:
   `9731349875117297474679317e925476` reads as `inf`. The draft report is
   `pypulseq-issues/09-signature-hash-as-number`. pypulseq master has the
   same code.
7. A file with `Hash` and no `Type` gives `signature_type == ""` and the
   hash. A file with `Type` and no `Hash` gives the type and
   `signature_value == ""`. (Verified by an edit of a written file.)

### 2.2 The run now

1. `run_checks` (`run.py:47`) reads a `.seq` path one time for each
   target, with the `Opts` of that target (`_read_sequence`, `run.py:182`).
   All the reads are of one file, so they give one signature.
2. A `Sequence` object gives exactly one target. The run uses the object
   as it is.
3. `ResultMatrix` (`results.py:164`) has `sequence`, `package_version`,
   `targets`, `results` and `analyses`. `from_json` refuses an unknown key
   and a missing key (`_check_keys`).
4. The JSON format stays 1 in the release candidates (the rule of the
   project). `0.1.0rc2` and `0.1.0rc3` added keys to format 1 in the same
   way (`findings`, `analyses`).

## 3. Design

### 3.1 `SequenceSignature` (`results.py`)

```python
@dataclass(frozen=True)
class SequenceSignature:
    """The signature of a Pulseq file: the `Type` and the `Hash` of its
    [SIGNATURE] section, as pypulseq read them. ..."""

    type: str
    hash: str
```

`__post_init__` raises `TypeError` when a field is not a `str`, and
`ValueError` when a field is empty. The run and `from_json` do not change
the text: no change of case and no check of the hex form. The package
exports it (`__init__.py`, `__all__`).

### 3.2 `ResultMatrix.sequence_signature`

```python
sequence_signature: SequenceSignature | None = None
```

It is the last field, with a default, so the existing calls of the
constructor stay valid. `None` means "no signature": the sequence that the
run checked has no `[SIGNATURE]` section (a file written with
`create_signature=False`, a file older than 1.4), or it is a `Sequence`
object that was not read from a file and not written. `with_max_findings`
and `without_series` keep it (they use `replace`).

### 3.3 The run (`run.py`)

A new function `_signature(seq, where) -> SequenceSignature | None`:

| `seq.signature_type` | `seq.signature_value` | Result |
|---|---|---|
| `""` | `""` | `None` |
| a `str` that is not empty | a `str` that is not empty | `SequenceSignature(type, hash)` |
| any other combination | | `RunError` (D3, D4) |

The `RunError` names the sequence and the two values with `repr`. For a
hash that is a number, the message says that pypulseq read the hash as a
number, so the hash text is lost (fact 2.1.6).

`run_checks` calls `_signature` for the sequence of each target, after the
read. The first call gives the signature of the matrix. A later call that
gives a different value is a `RunError` that names the two targets and the
two signatures (D5). For a `Sequence` object there is one call.

### 3.4 The JSON result

The key `"sequence_signature"` comes after `"sequence"`. Its value is
`null`, or `{"type": "md5", "hash": "..."}` with the keys in this order.
The key is necessary. `from_json` checks the keys of the object with
`_check_keys`, and a value that `SequenceSignature` refuses is a
`ValueError` (as `_finding_from_obj` does for a finding). `FORMAT` stays 1.

Thus a reader of `0.1.0rc5` refuses a result of `0.1.0rc6` (an unknown key
`sequence_signature`), and a reader of `0.1.0rc6` refuses a result of
`0.1.0rc5` (a missing key `sequence_signature`). No code reads the older
form (D6).

## 4. Tests

In `tests/test_run.py` (each test writes its file in `tmp_path`):

1. A file written with a signature: the matrix has the `Type` and the
   `Hash` of the `[SIGNATURE]` section of the file text. The test reads the
   two lines from the file, not from pypulseq.
2. The same file with two targets: one signature, the same as item 1.
3. A file written with `create_signature=False`: `None`.
4. A `Sequence` object: `None` for a new object with blocks; the signature
   of the file for an object that was read from a signed file; the hash
   that `seq.write` gave for an object that was written (fact 2.1.5).
5. A hash that pypulseq reads as a number: the test replaces the `Hash`
   line of a written file with 32 decimal digits (pypulseq does not verify
   the hash, fact 2.1.4). `RunError`.
6. A section with `Hash` and no `Type`, and a section with `Type` and no
   `Hash` (edits of a written file): `RunError`.
7. Different signatures for two targets of one file: the test wraps
   `run._read_sequence` with `monkeypatch`, and the wrapper changes
   `signature_value` of the second read. `RunError` that names both
   targets. The real reads of one file cannot give different signatures,
   so the test must make the second read different.

In `tests/test_results.py`:

8. The JSON round trip keeps the signature, with one and with `None`. The
   JSON text has the key after `"sequence"`.
9. `from_json` refuses a text without the key `sequence_signature` (the
   form of `0.1.0rc5`), a signature object with a missing or an unknown
   key, and a type or a hash that is empty or not a string.
10. `SequenceSignature` refuses an empty field and a field that is not a
    `str`.

`TESTS.md` gets an entry for each new test.

## 5. Decisions

- **D1. The name and the type** (approved 2026-10-05).
  `SequenceSignature(type, hash)`, a frozen dataclass, and the field
  `ResultMatrix.sequence_signature: SequenceSignature | None`. The JSON key
  is `"sequence_signature"`: `null` or `{"type": ..., "hash": ...}`.
- **D2. No verification of the hash** (approved 2026-10-05). The run
  records the signature that the file states. To verify it (the MD5 of the
  file text before `[SIGNATURE]`) is a separate item: `TODO.md` gets an
  entry.
- **D3. A hash that pypulseq read as a number is an error of the run**
  (approved 2026-10-05). The hash text is lost, so the run cannot record
  it. `TODO.md` gets an entry: when pypulseq reads the hash as text
  (`pypulseq-issues` 09), this error does not occur.
- **D4. A section that is not complete is an error of the run** (approved
  2026-10-05). A `Hash` without a `Type`, or a `Type` without a `Hash`
  (fact 2.1.7). The run records a signature only when it has both. The
  alternative is to record a `Hash` without a `Type` with `type == ""`,
  but then `SequenceSignature` must accept an empty type.
- **D5. Different signatures in one run are an error of the run** (approved
  2026-10-05). It cannot occur with the real reads (fact 2.2.1), so the
  check is a guard.
- **D6. The JSON of `0.1.0rc5`** (approved 2026-10-05). `from_json` refuses
  it (missing key). The CHANGELOG says so. No code reads the older form, by
  the rule of the release candidates.

## 6. How to execute this plan

1. **PR 1** (`docs/plan-signature`): this plan only.
2. **PR 2** (`feature/sequence-signature`, its own worktree): sections 3
   and 4 and the documentation of section 6.1, in one PR. Before the merge,
   set the status of this plan and fill in section 7.
3. **PR 3** (`chore/release-0.1.0rc6`): the version `0.1.0rc6` in
   `pyproject.toml`, `uv.lock` and `README.md:21`, the CHANGELOG heading,
   and the time budget (`scripts/budget.py`), as #56 did for `0.1.0rc5`.
   pulseq-analysis stays `v0.1.0rc5`. After the merge, the annotated tag
   `v0.1.0rc6` on the merge commit of `main`.

### 6.1 Documentation (in PR 2)

1. `docs/usage.md`:
   - Section 5, the list of exports: add `SequenceSignature`.
   - Section 5, `run_checks`, the list of the `RunError` cases: a
     signature that the run cannot record (D3, D4), and different
     signatures for the targets of one file (D5).
   - Section 5, the `ResultMatrix` table: the row `sequence_signature`,
     after `sequence`. A new subsection `SequenceSignature`: the two
     fields, and what "no signature" (`None`) means (section 3.2). Say that
     the run does not verify the hash, and that a `Sequence` object has
     the signature of the file that it was read from or written to, also
     after a change of its blocks (fact 2.1.5).
   - Section 6, the key table: the row `sequence_signature`, after
     `sequence`. The note of `format`: a reader of `0.1.0rc5` refuses a
     result of this version (unknown key), and this version refuses a
     result of `0.1.0rc5` (missing key).
   - Section 6, the JSON example: `"sequence_signature": {"type": "md5",
     "hash": "..."}` after `"sequence"`.
2. `CHANGELOG.md`, "Unreleased":
   - "Added": `SequenceSignature`, `ResultMatrix.sequence_signature`, and
     the JSON key `sequence_signature`.
   - "Changed": the JSON format 1 has the new key. `from_json` refuses a
     result of `0.1.0rc5` (missing key), and `0.1.0rc5` refuses a result
     of this version (unknown key). `run_checks` raises `RunError` for a
     signature that it cannot record (D3, D4).
3. `TODO.md`: the two entries of D2 and D3.
4. `TESTS.md`: the entries of section 4.

## 7. Results

(Filled in before the merge of PR 2.)
