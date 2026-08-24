## Security audit (generated)

**Gate:** PASS

### Release-surface identifier sweep (src/security/sweep.py)

- **Covers:** Every file `git ls-files` reports as tracked -- i.e. exactly what a reviewer receives on clone -- read as UTF-8 text and matched against seven identifier and credential patterns, each proven to fire on a planted canary in the same run.
- **Does NOT cover:** Untracked and gitignored files (including all of `data/`, `models/`, `.env` and `donations_inbox.jsonl`), which are audited separately because they are not released; binary files; git HISTORY, which holds files no longer tracked; and any identifier shape nobody thought to write a pattern for -- the same upper-bound caveat that `src/preprocessing/deidentify.py` carries. A clean result here is a statement about seven patterns over the tracked tree, not about the repository.
- **Detectors proven on this run:** yes

> Scanned 251 tracked text file(s); 0 skipped as undecodable; 5 excluded as self-referential (.env.example, .secrets.baseline, src/security/audit.py, src/security/sweep.py, tests/test_security.py).
> Detectors proved on the canary before the sweep ran: credential_assignment, email, phone_number, posix_home_path, private_key, social_handle, windows_user_path.
> 1 hit(s) suppressed by an inline `pragma: allowlist secret` waiver: docs/setup.md:125 (credential_assignment). Every waiver is listed here because a suppression nobody can total up is the `.secrets.baseline` problem written as a comment.

| severity | locator | finding | evidence (silhouette only) | fix |
|---|---|---|---|---|
| MEDIUM | `docs/consent_form.md:5` | email: an email address appears in a released file | `aaaaaaaaaa9@aaaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `docs/consent_form.md:100` | email: an email address appears in a released file | `aaaaaaaaaa9@aaaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `docs/ethics.md:424` | email: an email address appears in a released file | `aaaaaaaaaa9@aaaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `docs/ethics.md:510` | email: an email address appears in a released file | `aaaaaaaaaa9@aaaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `docs/open_issues.md:1139` | email: an email address appears in a released file | `aaaaaaaaaa9@aaaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `docs/recruitment.md:73` | email: an email address appears in a released file | `aaaaaaaaaa9@aaaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `docs/related_work.md:88` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `docs/related_work.md:88` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `docs/related_work.md:93` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `docs/related_work.md:93` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `docs/related_work.md:98` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `docs/related_work.md:98` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `docs/security.md:59` | phone_number: a digit run long enough to be a telephone number appears in a released file | `9999-99999` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `docs/security.md:162` | phone_number: a digit run long enough to be a telephone number appears in a released file | `9999-99999` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `paper/refs.bib:33` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `paper/refs.bib:129` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `paper/refs.bib:176` | phone_number: a digit run long enough to be a telephone number appears in a released file | `999-99999-9` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `phase9_handover.md:107` | email: an email address appears in a released file | `aaaaaa@aaaaaaa-aaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `scripts/run_preprocessing.py:79` | email: an email address appears in a released file | `a.aaaaa@aaaaaaa-aaaa.aaaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `src/preprocessing/deidentify.py:544` | email: an email address appears in a released file | `aaaaaa@aaaaaaa-aaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `tests/fixtures/deid_cases.jsonl:10` | email: an email address appears in a released file | `a.aaaaa@aaaaaaa-aaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `tests/fixtures/deid_cases.jsonl:26` | email: an email address appears in a released file | `aaaaaa@aaaaaaa-aaaa.aaa` | replace with a role address or remove; a personal address is an identifier |
| MEDIUM | `tests/fixtures/deid_cases.jsonl:11` | phone_number: a digit run long enough to be a telephone number appears in a released file | `99999 999999` | confirm it is not a contact number; remove it if it is |
| MEDIUM | `tests/test_preprocessing.py:210` | email: an email address appears in a released file | `a.aaaaa@aaaaaaa-aaaa.aaaa` | replace with a role address or remove; a personal address is an identifier |
| LOW | `docs/docker.md:92` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `docs/preprocessing.md:28` | social_handle: an @-handle appears in a released file | `@aaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `docs/security.md:152` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\a` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `docs/security.md:451` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `docs/security.md:283` | social_handle: an @-handle appears in a released file | `@aaaaaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `docs/security.md:283` | social_handle: an @-handle appears in a released file | `@aaaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `docs/setup.md:5` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `docs/setup.md:33` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `docs/setup.md:200` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `handover_phase_20.txt:296` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase10_handover.md:474` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase10_prompt.md:1` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase11_handover.md:228` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase11_handover_v2.md:187` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase12_handover.md:239` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase13_handover.md:267` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase1_summary.md:59` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase21_prompt.md:1` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase21_prompt.md:30` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase2_handover.md:33` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase2_handover.md:43` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase3_handover.md:4` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase3_handover.md:98` | social_handle: an @-handle appears in a released file | `@aaaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `phase3_handover.md:98` | social_handle: an @-handle appears in a released file | `@aaaaaaaaaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `phase4_handover.md:131` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase7_handover.md:221` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase7_handover.md:224` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase7_prompt.md:1` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase8_handover.md:284` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `phase9_handover.md:244` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `requirements.lock.txt:4` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\aaaaa` | replace with a relative path or `<REPO>` before the artifact is released |
| LOW | `scripts/run_preprocessing.py:82` | social_handle: an @-handle appears in a released file | `@aaaaaaaaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `src/preprocessing/normalize.py:4` | social_handle: an @-handle appears in a released file | `@aaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `src/preprocessing/pipeline.py:8` | social_handle: an @-handle appears in a released file | `@aaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `tests/fixtures/deid_cases.jsonl:8` | social_handle: an @-handle appears in a released file | `@aaaaaaaaaaaaaa` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `tests/fixtures/deid_cases.jsonl:26` | social_handle: an @-handle appears in a released file | `@aaaaaaaa_a` | confirm it is a placeholder; a real handle is a direct identifier |
| LOW | `tests/test_transformer.py:404` | windows_user_path: an absolute Windows path exposes the developer's account name | `A:\Aaaaa\a` | replace with a relative path or `<REPO>` before the artifact is released |

### detect-secrets baseline interrogation (src/security/baseline.py)

- **Covers:** The contents of `.secrets.baseline` itself: how many findings it suppresses, each entry's recorded audit verdict, whether its filenames and exclude patterns use the separators of the platform the gate runs on, and when it was generated.
- **Does NOT cover:** Whether the suppressed values are in fact harmless -- that judgement is made by a human and recorded in `docs/security.md` beside each entry, not by this code. It also does not run detect-secrets, does not scan the tree, and says nothing about files the baseline's exclude patterns remove from scope before scanning begins (currently: \.secrets\.baseline|\.env\.example|^data/|^paper/|^\.git/|^models/).
- **Detectors proven on this run:** yes

> Baseline generated 2026-08-12T13:35:43Z; 27 detector plugins configured; 4 finding(s) suppressed across 2 file(s).

No findings.

### Dependency advisory audit (src/security/deps.py)

- **Covers:** 180 exactly-pinned requirement(s) from requirements.lock.txt, each queried against the PyPI advisory service by name and upstream version, with local version segments such as `+cpu` normalised away.
- **Does NOT cover:** 19 floor-or-range requirement(s) from requirements-base.txt, requirements-ml.txt -- a range has no version to look up, so nothing here describes what `docker compose build` will actually install today. It also does not cover system packages from the images' `apt-get` layer, the base `python:3.11-slim` image itself, JavaScript or wheel-bundled native code, advisories published after the scan date, or whether a flagged code path is reachable from this project.
- **Detectors proven on this run:** yes

> Parsed 199 requirement line(s) across 3 file(s); 180 auditable, 19 not.

| severity | locator | finding | evidence (silhouette only) | fix |
|---|---|---|---|---|
| MEDIUM | `requirements.lock.txt:chromadb==1.1.1` | a published advisory affects this pinned version (GHSA-f4j7-r4q5-qw2c, PYSEC-2026-311) | -- | check for a fixed release; if none exists, record whether the vulnerable code path is reachable from this project |
| MEDIUM | `requirements-base.txt` | 12 requirement(s) state a floor or range rather than a version, so this file cannot be audited at all -- what gets installed is decided by pip at build time and differs between builds, and this is the file `Dockerfile (light image, and the base of the train image)` installs | -- | Phase 22 (reproducibility packaging): have the images install `requirements.lock.txt`, or generate a per-layer lock, so the audited versions and the shipped versions are the same versions |
| MEDIUM | `requirements-ml.txt` | 7 requirement(s) state a floor or range rather than a version, so this file cannot be audited at all -- what gets installed is decided by pip at build time and differs between builds, and this is the file `Dockerfile.train` installs | -- | Phase 22 (reproducibility packaging): have the images install `requirements.lock.txt`, or generate a per-layer lock, so the audited versions and the shipped versions are the same versions |
