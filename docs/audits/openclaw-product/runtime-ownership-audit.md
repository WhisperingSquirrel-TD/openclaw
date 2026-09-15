# Runtime ownership and deployment audit

**Audit mode:** read-only source/deployment ownership review. No runtime removal,
installation, live scheduler inspection, or external mutation was performed for
this report.

## 1. Determination

The repository has a clear **intended** deployment authority—the fork checkout
and `attached_assets/install-forked-openclaw.sh`—but it does not have a
single, statically provable runtime authority for every sidecar. The installer
owns most dynamically linked integrations, cron registrations, and generated
user services. Several checked-in service/timer pairs are not wired by that
installer, and one contains a path identity that conflicts with the
installer's `$HOME/openclaw` model while others lack a demonstrated deployment
path.

This is therefore an ownership and parity gap, not a deletion decision. The
audit found no basis for deleting a sidecar, snapshot copy, skill copy, task
worker, or recovery script. A snapshot disposition of `retire` or
`consolidate` remains an approval-gated proposal, not evidence of live
absence.

The most consequential contradiction is the expense watcher lifecycle:
current operating guidance says the former five-minute watcher timer is
disabled and that the central mirror router invokes `watcher.py` as its
`ExecStartPost`, while the checked-in `expense-intake-watcher.timer` still
declares a five-minute trigger. Without read-only live unit/timer state, this
must be treated as a possible duplicate lifecycle.

## 2. Counted scope and evidence boundary

| Scope item                                           |                                                              Count | What the count means                                                                                                      |
| ---------------------------------------------------- | -----------------------------------------------------------------: | ------------------------------------------------------------------------------------------------------------------------- |
| Snapshot manifest entries                            |                                                            **226** | All entries were read and byte-checked; this is the supplied review snapshot, not live state.                             |
| Snapshot bytes                                       |                                                      **2,542,148** | Manifest and observed bytes agree; zero byte mismatches.                                                                  |
| Snapshot skill entries                               |                                                             **55** | The activation matrix's declared skill scope; textual triggers are not scheduler proof.                                   |
| Exact local content matches                          |                                                             **36** | Hash matches in tracked files or `.local/intake-repair`; not proof of deployment.                                         |
| Same-relative-path candidates                        |                                                             **69** | Path candidates only; not content or consumer proof.                                                                      |
| Snapshot dispositions                                | **31 keep, 168 investigate, 13 consolidate, 2 retire, 12 connect** | Conservative audit labels, not implementation or deletion instructions.                                                   |
| Workspace Control Panel/task-system snapshot entries |                                                             **41** | All are `investigate`; none has an exact local counterpart in the inventory search.                                       |
| Checked-in systemd/timer unit files                  |                                              **6 files / 3 pairs** | SharePoint backup, expense watcher, and auth monitor pairs.                                                               |
| Installer OS-cron registration families              |                                        **14 conditional families** | The installer can register fourteen distinct crontab lines/families; this is not a live crontab count.                    |
| Installer-generated user-service unit names          |                                                              **6** | One management-bot service, four email/calendar services, and one Google-calendar service.                                |
| Attached skill directories                           |                                                             **12** | Product/development skill sources under `attached_assets/skills`; behavior and live skill coverage are out of scope here. |
| Explicit setup-dev skill names                       |                                                             **10** | The first skill deployment loop; the later installer loop writes the same destination again.                              |

The inventory records the remote commit as
`faa717afeb66322a79e5eb20ebf8b27fec83042d`, but also records that the commit
object is unavailable in this checkout and that live scheduler/runtime access
was blocked ([inventory provenance](entry-inventory.json#L12-L45)). Its decision
legend explicitly says that `keep`, `connect`, `consolidate`, `retire`, and
`investigate` do not establish live use ([inventory](entry-inventory.json#L47-L60)).
The activation matrix likewise separates declared trigger text from proven
runtime activation ([review brief](review-brief.md#L28-L32)).

The separate product-wide live-skill review is not repeated here. Skill
behavior, quality, and coverage are out of scope; this report only establishes
which source tree wins when the installer copies or links a skill.

## 3. Ownership map

### 3.1 Installer and source checkout

The installer first pulls or clones `$HOME/openclaw`, then copies the freshly
pulled installer to `$HOME/install-forked-openclaw.sh` and re-execs it
([installer:92-135](../../../attached_assets/install-forked-openclaw.sh#L92-L135)).
Its integration source root is
`$HOME/openclaw/attached_assets/integrations`; the normal deployment primitive
is a symlink into `~/.openclaw/integrations`
([installer:932-976](../../../attached_assets/install-forked-openclaw.sh#L932-L976)).
This establishes the intended source identity:

```text
Git checkout:       $HOME/openclaw
integration source: $HOME/openclaw/attached_assets/integrations
runtime destination: $HOME/.openclaw/integrations
user units:         $HOME/.config/systemd/user
```

The installer is documented as the single deployment authority
([pi-deployment.md:21-24](../../../knowledge/pi-deployment.md#L21-L24)), but
that claim is not true for every checked-in unit: the gaps below are exactly
why an installer rule is not live deployment proof.

### 3.2 Checked-in systemd/timer units: six files, three ownership states

| Checked-in pair                                                                | Source-controlled evidence                                                                                                                                                                                                                                                                                               | Ownership/parity result                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `attached_assets/systemd/user/openclaw-sharepoint-backup.service` and `.timer` | The service executes `/home/tomdean88/.openclaw/integrations/microsoft/sharepoint_backup.py`; the timer runs daily at 03:30 London ([service](../../../attached_assets/systemd/user/openclaw-sharepoint-backup.service#L1-L12), [timer](../../../attached_assets/systemd/user/openclaw-sharepoint-backup.timer#L1-L10)). | The script exists under `attached_assets/integrations/microsoft/sharepoint_backup.py`, but the installer's explicit integration deployment list does not deploy it ([source](../../../attached_assets/integrations/microsoft/sharepoint_backup.py#L15-L32), [installer list](../../../attached_assets/install-forked-openclaw.sh#L949-L976)). The pair is therefore a checked-in artifact with no demonstrated installer owner.                                             |
| `pi-services/systemd-user/expense-intake-watcher.service` and `.timer`         | The service hardcodes `/home/tomdean88/openclaw/pi-services/.../watcher.py`; the timer runs every five minutes ([service](../../../pi-services/systemd-user/expense-intake-watcher.service#L1-L9), [timer](../../../pi-services/systemd-user/expense-intake-watcher.timer#L1-L11)).                                      | The operating guide says the former five-minute timer is disabled and the central router calls the executor as `ExecStartPost` ([OPERATING.md:9-17](../../../pi-services/expense-intake-watcher/OPERATING.md#L9-L17)); it also identifies the mirror router and enrichment timer as the active triggers ([OPERATING.md:54-64](../../../pi-services/expense-intake-watcher/OPERATING.md#L54-L64)). This pair is a possible duplicate trigger, not a safe deletion candidate. |
| `scripts/systemd/openclaw-auth-monitor.service` and `.timer`                   | The service executes `/home/admin/openclaw/scripts/auth-monitor.sh`; the timer repeats every 30 minutes ([service](../../../scripts/systemd/openclaw-auth-monitor.service#L1-L14), [timer](../../../scripts/systemd/openclaw-auth-monitor.timer#L1-L10)).                                                                | The checked-in executable is `scripts/auth-monitor.sh`, and the optional setup script copies only the two units into the user's systemd directory ([setup-auth-system.sh:63-81](../../../scripts/setup-auth-system.sh#L63-L81)). The `/home/admin` identity conflicts with the installer's `/home/tomdean88` examples and is not deployment proof.                                                                                                                          |

No live `systemctl --user` state, unit fragment path, timer state, or crontab
was inspected. The six files prove source-controlled declarations only.

### 3.3 Dynamically generated services

The installer writes the management-bot unit directly into
`$HOME/.config/systemd/user` ([installer:1500-1559](../../../attached_assets/install-forked-openclaw.sh#L1500-L1559)).
It then writes four poller services—Microsoft email, assistant email,
Microsoft calendar, and Gmail email—and later writes Google Calendar
([installer:1727-1836](../../../attached_assets/install-forked-openclaw.sh#L1727-L1836);
[Google Calendar:1954-1975](../../../attached_assets/install-forked-openclaw.sh#L1954-L1975)).
That is **six resulting generated service names**. The assistant service is
written once and conditionally rewritten with a token path, but remains one
unit name.

The gateway is a separate seventh lifecycle boundary: the installer does not
generate its unit; it patches an already existing
`openclaw-gateway.service`, reloads systemd when needed, and prefers a systemd
restart with `l1-start.sh` as fallback
([installer:2008-2085](../../../attached_assets/install-forked-openclaw.sh#L2008-L2085)).
The gateway unit's originating file, checkout, and hash therefore require live
source-map evidence before an installer result can be called current.

### 3.4 Installer OS-cron families

The **fourteen** conditional registration families are:

| Family                     | Cadence                              | Installer evidence                                                           |
| -------------------------- | ------------------------------------ | ---------------------------------------------------------------------------- |
| Garmin Connect poller      | Daily 09:00                          | [1040-1048](../../../attached_assets/install-forked-openclaw.sh#L1040-L1048) |
| Daily provider reset       | Daily 04:00                          | [1067-1081](../../../attached_assets/install-forked-openclaw.sh#L1067-L1081) |
| Codex token keeper         | Every 20 minutes                     | [1086-1102](../../../attached_assets/install-forked-openclaw.sh#L1086-L1102) |
| CRM lead importer          | Daily 08:00                          | [1107-1122](../../../attached_assets/install-forked-openclaw.sh#L1107-L1122) |
| System health check        | Daily 06:55                          | [1127-1147](../../../attached_assets/install-forked-openclaw.sh#L1127-L1147) |
| Prospector queue processor | Every 30 minutes                     | [1173-1195](../../../attached_assets/install-forked-openclaw.sh#L1173-L1195) |
| SharePoint cache poller    | Every 15 minutes                     | [1265-1285](../../../attached_assets/install-forked-openclaw.sh#L1265-L1285) |
| SharePoint queue processor | Every minute                         | [1290-1313](../../../attached_assets/install-forked-openclaw.sh#L1290-L1313) |
| SharePoint housekeeping    | Nightly 02:00                        | [1318-1335](../../../attached_assets/install-forked-openclaw.sh#L1318-L1335) |
| Stackstone report poller   | Every 5 minutes                      | [1340-1356](../../../attached_assets/install-forked-openclaw.sh#L1340-L1356) |
| Stackstone enquiry poller  | Every 2 minutes                      | [1361-1378](../../../attached_assets/install-forked-openclaw.sh#L1361-L1378) |
| YouTube channel poller     | Every 30 minutes outside 06:xx–07:xx | [1394-1425](../../../attached_assets/install-forked-openclaw.sh#L1394-L1425) |
| AI briefing                | Mondays 06:00                        | [1440-1488](../../../attached_assets/install-forked-openclaw.sh#L1440-L1488) |
| WhatsApp rolling file      | Every 15 minutes                     | [1592-1611](../../../attached_assets/install-forked-openclaw.sh#L1592-L1611) |

These are source registrations, not evidence that all fourteen lines exist in
the current crontab. The installer removes matching lines only within each
family and does not inventory unrelated jobs.

There is also the native OpenClaw cron subsystem in `src/cron/` and the
systemd-timer subsystem above. Those are separate scheduler mechanisms and
must not be collapsed into an OS-cron count.

### 3.5 Copied-skill precedence

`scripts/setup-dev-workflow.sh` declares ten named skills and links each from
`$REPO_DIR/attached_assets/skills` into `~/.openclaw/skills`
([setup-dev-workflow.sh:46-70](../../../scripts/setup-dev-workflow.sh#L46-L70)).
The installer invokes that script first, then loops over every directory under
`$HOME/openclaw/attached_assets/skills` and links each `SKILL.md` into the
same destination ([installer:2255-2291](../../../attached_assets/install-forked-openclaw.sh#L2255-L2291)).

The ten setup names are all present in the twelve-directory attached source
family. Consequently:

- the later attached-assets loop is the effective final writer for all ten
  overlapping names;
- `expenses` and `finance` are written only by the later loop;
- a retired-skill marker can remove the destination before skipping it
  ([installer:2272-2288](../../../attached_assets/install-forked-openclaw.sh#L2272-L2288));
- this is a deployment-precedence fact, not proof that a live runtime loaded
  any of the links.

The knowledge file instead describes workspace skills under
`~/.openclaw/workspace/skills/` and system skills under
`~/.openclaw/skills/` ([skills.md:6-9](../../../knowledge/integrations/skills.md#L6-L9)).
That documentation and the installer therefore describe different skill
locations. It must be reconciled by a source/deployment owner; this audit does
not move or remove either tree.

## 4. Task, continuation, and worker lifecycle ownership

The current checkout has a canonical task-system adapter that requires a local
HTTP gateway and is owner-only ([task-system-tool.ts:73-90](../../../src/agents/tools/task-system-tool.ts#L73-L90);
[279-285](../../../src/agents/tools/task-system-tool.ts#L279-L285)). It is not
the same source path as the snapshot's
`workspace/projects/workspace-control-panel/pi-gateway/src/task-system.js`.
All 41 snapshot entries matching the Workspace Control Panel/task-system
family are `investigate`, with no exact local counterpart recorded by the
inventory. That is a source-identity/runtime-parity gap, not proof that the
snapshot service is obsolete or that the current local adapter is deployed.

The retained continuation implementation has one durable owner:

- state is versioned with explicit terminal states, generation, revision, and
  persisted work ([continuation-loop.ts:17-69](../../../src/agents/continuation-loop.ts#L17-L69));
- state transitions are lock-protected and atomically persisted
  ([continuation-loop.ts:191-248](../../../src/agents/continuation-loop.ts#L191-L248));
- leases and idempotency keys gate work claims
  ([continuation-loop.ts:595-635](../../../src/agents/continuation-loop.ts#L595-L635));
- `continuation-scheduler.ts` is explicitly the only place that turns durable
  state into queue work ([continuation-scheduler.ts:26-35](../../../src/auto-reply/reply/continuation-scheduler.ts#L26-L35));
- restart recovery rehydrates persisted envelopes and retries after lease
  expiry ([continuation-recovery.ts:31-95](../../../src/auto-reply/reply/continuation-recovery.ts#L31-L95));
- subagent list, kill/cascade, and steer operations are owned by the
  `subagents` tool ([subagents-tool.ts:349-355](../../../src/agents/tools/subagents-tool.ts#L349-L355);
  [446-547](../../../src/agents/tools/subagents-tool.ts#L446-L547);
  [548-703](../../../src/agents/tools/subagents-tool.ts#L548-L703)).

This is enough to identify the canonical **current-checkout** lifecycle. It is
not enough to claim that a separate WCP gateway, worker wrapper, or snapshot
continuation process is absent from a Pi. The source snapshot must remain
retained until deployment parity is proved.

## 5. Contradictions requiring ownership decisions

### A. “Single installer authority” versus unowned checked-in units

The installer authority rule says an un-wired file is not deployed, but the
SharePoint backup pair and expense watcher pair are checked in without an
installer deployment step. The auth pair has a separate interactive setup
script. This creates three possible owners—installer, manual setup, or an
older Pi deployment—for units that cannot be assigned from repository text
alone.

### B. `$HOME/openclaw` versus hardcoded `/home/admin`

The installer updates `$HOME/openclaw` and deploys from its
`attached_assets` tree. The auth service instead executes
`/home/admin/openclaw/scripts/auth-monitor.sh`, while the current source is
`scripts/auth-monitor.sh`. A unit path is not a source identity unless the
target path and target hash are read-only verified on the live host.

### C. Expense timer versus central router

The checked-in timer says every five minutes. The operating guide says that
timer is disabled and that `openclaw-mirror-router` owns the ordered trigger.
If both are enabled, the watcher can receive duplicate invocations. The
watcher has state/idempotency safeguards, but those safeguards do not make two
schedulers an owned design.

### D. 06:xx/07:xx policy versus installed schedules

The knowledge rule prohibits new jobs in 06:xx and 07:xx and says timed tasks
should be 08:00 or later ([pi-deployment.md:103-105](../../../knowledge/pi-deployment.md#L103-L105)).
The installer nevertheless explicitly installs health at 06:55 and AI briefing
on Monday at 06:00 ([installer:1127-1147](../../../attached_assets/install-forked-openclaw.sh#L1127-L1147);
[1440-1488](../../../attached_assets/install-forked-openclaw.sh#L1440-L1488)).
The YouTube exclusion of 06:xx–07:xx does not resolve those other two
contradictions. This report records the contradiction and does not repair a
schedule.

### E. Attached/workspace source mismatch

The snapshot's dominant paths are `workspace/...`, including
`workspace/projects/workspace-control-panel/...`, while the installer deploys
from `$HOME/openclaw/attached_assets/...`. The inventory's same-relative and
hash-match counts are useful comparison evidence, but they do not bridge those
roots or establish a deployed checkout. Any proposal to replace a snapshot
worker with a current source file must first identify the live checkout,
profile, state directory, unit, and port.

### F. Snapshot task-system evidence versus current canonical adapter

The 41 WCP/task-system snapshot entries are all `investigate`, while the
current checkout owns a local, bearer-authenticated task-system adapter and a
durable continuation implementation. The two are not interchangeable merely
because their names overlap. The correct status is “current implementation
retained; snapshot service parity unproven.”

## 6. Potentially obsolete families: status and no-delete gates

The following are the families most likely to be mistaken for obsolete
copies. None is approved for removal:

| Candidate family                            | Current evidence                                                                                                                                                                                        | Required status before any deletion                                                                                                                                                                                                                 |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Garmin cookie poller                        | The installer removes `poll-garmin-cookie.py` and replaces matching Garmin cron lines with the library poller ([installer:1008-1048](../../../attached_assets/install-forked-openclaw.sh#L1008-L1048)). | Verify the live target has the library poller, token/auth path, last successful output, and no remaining unit/cron/command references to the cookie poller. The installer’s `rm -f` is not retrospective proof that every installation is migrated. |
| Five-minute expense watcher unit/timer      | Current guide says the timer is retired; checked-in timer still declares it.                                                                                                                            | Prove live timer state, central-router `ExecStartPost`, queue/state ownership, one complete interval without duplicate effects, and rollback before disabling or deleting either declaration.                                                       |
| SharePoint backup service/timer             | Checked in, but backup script is not in the installer’s explicit deployment list.                                                                                                                       | Prove unit fragment, deployed script hash, import path, credentials/profile, timer state, backup receipt, and replacement/rollback owner.                                                                                                           |
| Auth monitor pair                           | Checked in and manually installable, but service path says `/home/admin`.                                                                                                                               | Prove the actual user, executable realpath/hash, unit state, setup owner, notification destination, and replacement monitor before changing the path or retiring the pair.                                                                          |
| WCP/task-system snapshot workers            | 41 `investigate` entries with no exact local counterpart; current main has a different canonical adapter.                                                                                               | Identify any live WCP checkout, gateway port, process/unit, task database/state, email-dispatch boundary, and consumer graph. Missing local files are not absence evidence.                                                                         |
| AI-briefing outbound runner snapshot family | Six entries are `consolidate` candidates in the inventory; the installer instead deploys the attached AI briefing pipeline.                                                                             | Prove whether the outbound runner is live, identify its queue/database and destination receipts, compare outputs and failure handling, then obtain owner approval for a bounded migration.                                                          |
| Duplicate skill copies                      | The setup loop and later extra-skill loop both write `~/.openclaw/skills`; knowledge describes a different workspace path.                                                                              | Record each realpath/hash, configured skill roots, loader precedence, consumers, and a rollback copy before consolidating.                                                                                                                          |
| Generated/example snapshot artifacts        | Inventory labels two entries `retire`, but explicitly requires owner confirmation.                                                                                                                      | Confirm no live/static/dynamic consumer, preserve provenance, obtain owner sign-off, and execute a separately reviewed deletion batch.                                                                                                              |

### Exact no-delete gates

No candidate may be deleted, disabled, or redirected until **all** gates below
are recorded for that candidate:

1. **Live source identity.** Record the deployed realpath, symlink target,
   SHA-256, checkout root, Git commit, and relevant profile/state directory.
   The source hash must match the named repository artifact or a documented
   migration target. A relative path, filename, or unit declaration alone
   fails this gate.
2. **Complete scheduler inventory.** Record `systemctl --user cat/show`,
   enabled/active state, `list-timers --all`, the complete user crontab, and
   native OpenClaw cron jobs for the owning user. Include generated units and
   manually installed units; do not infer absence from repository search.
3. **Consumer and boundary graph.** Trace source → scheduler/router → worker →
   state/queue → downstream destination → receipt. Include dynamic references,
   subprocess calls, symlinks, shared state files, and task/email dispatch
   boundaries. “No static consumer found” fails this gate.
4. **Replacement parity.** If a replacement exists, compare behavior,
   cadence, input coverage, idempotency, leases/locks, terminal states,
   failure/blocked behavior, auth boundaries, and output/receipt formats.
   Run the focused regression suite and one controlled end-to-end interval
   under the approved operator procedure.
5. **Data and rollback protection.** Capture required state, queue, ledger,
   and receipt backups; document the exact rollback source/hash and restore
   command. For a timer, prove that disabling it cannot strand pending work.
6. **Duplicate-lifecycle proof.** Show which scheduler is the sole owner and
   prove that every competing trigger is disabled or deliberately retained
   with an idempotency contract. For the expense watcher, this specifically
   requires reconciling the five-minute timer with the mirror-router
   `ExecStartPost`.
7. **Owner approval and change record.** Record the human owner, candidate
   path/unit/skill name, reason, evidence links, deletion batch, and approval
   before any destructive action. Snapshot `retire` and `consolidate` labels
   do not satisfy this gate.

### Minimum evidence bundle to obtain next

The next read-only deployment review should collect, for each active user and
each suspected service:

- unit fragment path and rendered `ExecStart`/`WorkingDirectory`;
- `readlink -f` and SHA-256 for every executable and linked skill;
- checkout root, Git commit, clean/dirty status, and installer revision;
- user crontab, native OpenClaw cron catalogue, and all user timers;
- gateway/process/port ownership for the task-system and WCP candidates;
- runtime state roots, queue files, receipt/audit paths, and last-success
  timestamps;
- source-to-destination hashes for the six checked-in unit files (three pairs)
  and the six installer-generated service names;
- a full-schedule observation or equivalent controlled proof for any lifecycle
  proposed for consolidation.

These are evidence requirements, not commands executed by this audit.

## 7. Result and boundary

No runtime component was removed, disabled, deployed, or rewritten. The
current checkout's canonical continuation/task implementation remains retained;
the snapshot WCP/task-system family remains an unresolved parity question.
Installer-generated cron/service ownership, checked-in unit ownership, and
copied-skill precedence are now documented with source line citations.

The only accompanying documentation correction is the stale native-Git rule in
`replit.md`; no runtime code or deployment artifact is changed by this audit.
