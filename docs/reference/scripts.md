# Governance Scripts

## Evaluation chain (`kanban_evaluation_chain.py`)

```bash
python kanban_evaluation_chain.py <task_id> <workspace> --baseline HEAD~1
```

6-step Deterministic Adjudication Lattice. Each step returns ALLOW/DENY with error code:

1. **Files: compliance** (E001) — every file in `Files:` has >0 changes
2. **Unlisted changes** (E002) — auto-revert files outside `Files:`
3. **Test pass** (E003) — run `Tests:` command
4. **Commit match** (E004) — commit message matches `Commit:` line
5. **Token log** (E005) — `token_tracker.py` produced a log entry
6. **Zero-output check** (E006) — at least one file has >0 diff

Lattice memory: successful completions are cached as attractors. Subsequent workers with matching file+test hash skip steps 1, 3, 4.

## Attestation (`kanban_attestation.py`)

```bash
python kanban_attestation.py <plan_id>                    # generate
python kanban_attestation.py <plan_id> --verify            # check validity
```

Generates `$HERMES_HOME/kanban/attestation.yaml` after preflight. Records: preflight status, profile validity, agent-prompt block count. Session-scoped (120 min TTL). Error codes: A001 (missing), A002 (stale), A003 (tampered).

## Card body policy (`kanban_card_policy.py`)

```bash
python kanban_card_policy.py --all --profile balanced       # validate all cards
python kanban_card_policy.py <task_id>                      # validate one card
```

Validates card bodies against `policies/card-body-policy.yaml`. Blocks cards missing `Files:`, `agent -p` block, or `Mode:`. Supports advisory/balanced/strict profiles.

## Recovery (`kanban_recover.py`)

```bash
python kanban_recover.py <task_id> <error_code>             # single recovery
python kanban_recover.py --cascade                          # triage multi-failure
python kanban_recover.py --list                             # list all recovery actions
```

Maps 23 error codes to recovery actions. Cascade triage: pause downstream → env first → agent second → governance infra last → verify.
