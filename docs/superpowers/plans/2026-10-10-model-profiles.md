# Model profiles implementation plan

> **For agentic workers:** Use executing-plans; implement and verify each task in order.

**Goal:** One keyboard model picker and one reusable form for adding, editing and switching saved models.

**Architecture:** SettingsStore owns atomic profile migration and active selection. A dedicated prompt_toolkit module owns the picker/form. Application coordinates persistence and connection checks; the answer summary refreshes its config after management.

**Tech Stack:** Python >=3.9, existing prompt_toolkit and Rich; no new dependencies.

**Spec:** User-approved chat design: arrows/Enter to switch, e to edit, a visible add row, Tab between fields, masked Key, save and test, delete within editor, same picker from settings and answer summary.

## Constraints and decisions

- Preserve legacy credentials and health by lazily migrating the single ai config on the next profile write, atomically with that operation.
- Profile display name is its model; endpoint distinguishes identical names. No extra nickname field.
- Adding saves independently; first profile activates automatically. Existing profiles keep their active selection until explicitly selected.
- Editing preserves profile ID and active selection. Blank Key reuses only at the same normalized service URL.
- Delete requires confirmation. Deleting the active profile leaves no active model until the user selects one, never silently changes providers.
- Tests are offline with synthetic credentials. No real platform papers or saved keys are read.
- Keep current checkout so the user's normal launch sees changes; no automatic push.

## Review focus

Canceled forms must never mutate saved credentials; switching after task selection must use the new model for testing and answering; invalid old config must not be silently discarded; health cannot survive credential edits; failed disk writes must preserve the previous active profile and all unrelated settings.

### Task 1: Profile storage

- [x] Add tests in tests/test_model_profiles.py for migration, switching/restart, editing, health isolation, deleting active, corrupt data and failed atomic writes; run and observe failure.
- [x] Extend settings.py with ai_profiles(), save_ai_profile(config, profile_id=None), activate_ai_profile(id), delete_ai_profile(id), preserving ai_config()/save_ai()/ai_health() compatibility.
- [x] Run storage tests and existing settings/health tests.

### Task 2: Picker and form

- [x] Add pipe-input tests in tests/test_model_ui.py for arrows/Enter, add/edit/cancel, Tab editing, blank-key reuse and replacement validation, masking and deletion.
- [x] Implement model_ui.py with choose_model(rows, active_id, ...) and edit_model(current=None, ...); TerminalUI adapts these plus non-TTY input.
- [x] Run UI tests including existing UI suite.

### Task 3: Integration

- [x] Add tests for managing profiles with automatic connection test, cancel/delete, and switching inside an existing answer summary without losing selected tasks/options.
- [x] Implement Application.manage_models(), connect settings and summary m action, ensure all callbacks use current config rather than stale closure.
- [x] Update usage docs; run full unittest suite, compileall, diff check; inspect native UI at narrow and normal widths; request independent review and fix material findings.

## Verification and review

- Baseline: 159 unittest cases passed.
- Final: 178 unittest cases passed; compileall and git diff --check passed.
- Native picker and editor exercised with pipe input and PTY preview. Password rendering verified at 40, 52 and 80 columns using synthetic credentials.
- Independent read-only review found fixed-width editor buttons inaccessible at 40 columns. Regression reproduced before fix; responsive vertical buttons resolve it, full suite green afterward.
- Read-only legacy projection avoids changing the user's real config until they save/select a profile. No real credentials or provider/platform requests were used during verification.
- Identical endpoint/model/key combinations intentionally share a health identity; malformed profiles fail without overwriting data.
- User requested committing and pushing this work after unifying Esc navigation.

## Follow-up: unified Esc navigation

- [x] Replaced native line input with prompt_toolkit PromptSession so Esc returns immediately without Enter, including hidden inputs; arrow sequences still edit text.
- [x] Unified visible navigation hints across menus, summaries, pickers and model forms. Existing b input remains an undocumented compatibility alias.
- [x] Esc pauses manual answers while preserving completed work. Esc from connection results returns to settings; Esc from deletion confirmation returns to the editor.
- [x] Added native-input and hierarchy regressions. Full suite: 184 cases passed; compileall and diff checks passed.
