# Install and optional unattended repository updates

This updater is **separate from health-data notifications**. It may be enabled during installation when the owner explicitly requests repo synchronization, as long as the agent has verified the exact trusted source. Do not infer consent for food ideas, journal reminders, weekly feedback, publishing, or any message delivery.

Trusted source: [`PotapKong/fitness-coach-hermes`](https://github.com/PotapKong/fitness-coach-hermes), branch `main`, MIT. The script in this repository hardcodes the HTTPS origin and branch and checks the fetched SHA. It is not a malware sandbox or cryptographic author signature: trusting automatic **code** updates means trusting the maintainer's GitHub account and repo. If that is unacceptable, use `--check` and review changes manually before applying.

## Install on Hermes

Requires `git`, Python 3.10+, HTTPS access to GitHub, and the Hermes CLI. Optional Pillow and a Cyrillic TTF are required for local PNG cards; logging and text summaries use the standard library. Install the separate official `fitness-nutrition` skill only if you want its exercise references; this repository does not bundle it.

```bash
hermes skills install official/health/fitness-nutrition
# Inspect this repository and updater before executing it.
git clone https://github.com/PotapKong/fitness-coach-hermes.git
python3 fitness-coach-hermes/update_skill.py --check
python3 fitness-coach-hermes/update_skill.py --apply
# For this runtime's --script --no-agent cron, install a stable script copy.
mkdir -p "$HOME/.hermes/scripts"
cp fitness-coach-hermes/update_skill.py "$HOME/.hermes/scripts/fitness-coach-update.py"
python3 "$HOME/.hermes/scripts/fitness-coach-update.py" --check
```

`--apply` installs an allowlisted package behind an atomic managed symlink at `~/.hermes/skills/fitness-coach-hermes/`, records `.upstream-sha`, and retains prior release directories under `~/.hermes/skill-releases/fitness-coach-hermes/` (outside the skill discovery directory). It refuses an existing ordinary directory, unmanaged link or unexpected files. If you already installed a copy manually, **inspect and back it up first**; move only the code package aside, never delete private journals/configuration. Keep `COACH_DATA_DIR` and any preference profile in a private directory **outside** the skill/repo. Do not move real health data into the skill directory. The updater does not use GitHub credentials, user logs or a Telegram route. Its atomic symlink swap requires POSIX (Linux/macOS); on Windows/WSL use WSL's Linux Python and filesystem or review-only mode.

Before enabling the job, test `--apply` against a disposable target with `--target /absolute/disposable/fitness-coach-hermes`, confirm the installed SHA and tests, and remove that disposable copy. Do not put a private journal in the disposable directory. Then, on Hermes:

```bash
hermes cron create 'every 24h' \
  --name fitness-coach-hermes-updater \
  --script fitness-coach-update.py \
  --no-agent --deliver local --failure-deliver local
hermes cron list
```

The script is intentionally quiet when the installed SHA matches upstream. When upstream changes, it clones the fixed public repo, checks the exact head SHA, parses Python without executing new code, checks required package files and recipe IDs/URLs, stages an owner-only copy, and atomically swaps a pointer to the installed skill. It never copies `.git/`, `private-data/`, `.env`, real cards or profiles. On failure or interruption before the pointer swap, the prior release stays active; errors exit nonzero and appear in local cron state. A new agent session or `/reload-skills` may be needed to load changes. It does **not** auto-update the stable cron script itself. **Before updating to this release** (which adds `automation_core.py` and `history_db.py`), an older cron script with a fixed file allowlist can install only the old package subset while advancing its SHA. Manually review and recopy the latest `update_skill.py` into `~/.hermes/scripts/fitness-coach-update.py` **before the next scheduled run**, then run `--apply` and confirm both new files exist. If an old script already advanced the SHA, the new script detects missing required files and repairs the package on `--apply`. Newer scripts refuse unknown top-level Python files. Review all updater changes before recopying; this is a deliberate supply-chain trust boundary.

To test the schedule once, get the real job ID from `hermes cron list`, then run `hermes cron run JOB_ID` and check the resulting run state plus `.upstream-sha`. Do not claim that a successful `cron create` proves the job will fire later. Check scheduler state with the current Hermes documentation: https://hermes-agent.nousresearch.com/docs/user-guide/features/cron . If your agent/runtime is not Hermes, follow its own scheduler documentation; never invent CLI flags or destination IDs.

**Boundary:** This automatic sync follows the public `main` code branch; validation catches missing files, syntax and catalog structure, but cannot prove new code is benevolent, clinically safe or functionally correct. For a stricter supply-chain policy, create only a daily `--check` job and require human approval before applying code diffs. Never create morning recipe ideas, journal reminders, or external delivery jobs as part of this install; first use the per-person consent procedure in `AUTOMATION.md`.
`--check` makes a remote SHA lookup and local reads only; it does not create the target directory or lock file. `--apply` may create those files and install a new managed release.
