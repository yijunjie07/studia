# Manual Answer Continuation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the runner integration; UI is delegated with a fixed callback contract.

**Goal:** Let the user answer an unresolved question in place and resume saved work without regenerating completed answers; simplify the start screen.

**Architecture:** AnswerRunner accepts a manual_answer(question, reason) callback returning a typed answer or None to pause. TerminalUI owns input and suspends its live display. Reports checkpoint pending questions and validated answers; matching saved answers are reused after reading the current paper and verifying identity/content.

**Tech Stack:** Python 3.9, Rich, unittest.

**Spec:** User request in this conversation, 2026-10-10: show failed question/options for manual entry, preserve answers, avoid generic failure and repeated explanation.

## Constraints

- Preserve existing uncommitted work; no commits or real submissions required.
- Keep submission deduplication, clock checks, answer encoding and ownership checks.
- Manual input cannot bypass structural validation or guess unsupported media.
- User-selected report-only mode still does not submit.

## Tasks

- [x] Add failing tests for manual completion after retries/low confidence, pause/resume and stale-answer rejection.
- [x] Add runner manual callback/checkpoints and validated answer reuse (including compatible existing reports).
- [x] Wire callback, paused status and compact result messages in the application.
- [x] Implement/test manual terminal entry and simplify summary (delegated ui.py).
- [x] Run targeted tests, full suite, static checks, and focused review; document behavior.

Validation: 159 offline tests pass; compileall and git diff --check pass. Focused review found and fixed service-error resume classification and manual-answer preservation when time expires. Terminal output checked at 52 and 80 columns. No real platform attempts or submissions were made for this feature.

## Review Focus

- B must be a choice answer rather than navigation.
- Changed options or parent context must invalidate cached answers.
- Pausing must preserve current question and completed answers without submitting.
- Expired time or changed platform submission must block submission after manual entry.
- Unsupported media/unknown types must remain unsubmitted and keep prior answers.
