# OpenClaw product reconciliation audit - current SkilzVolt skills (non-cartoon scope)

**Catalogue revision:** `b95e7feae0186f85306d6000a48ca6c144aeec030d58cfc5e7e171931cb79b12` | **Assigned:** 32 | **Included:** 27 | **Excluded by owner:** 5

## Executive result

This is a read-only reconciliation of the current approved catalogue and all 27 assigned non-cartoon skills. The five cartoon skills are recorded separately as **excluded by owner instruction**, not as failed or unverified. Current SkilzVolt metadata/body retrieval was complete for all 32 assignments; no live runtime activation is inferred from prose.

The checkout proves a generic owner-only SkilzVolt adapter and a small set of native/bundled routes. It does **not** prove that each remote current body is installed, scheduled, executed, delivered, or read back. Declared cron times are claims until live scheduler and receipt evidence is available.

### Included disposition counts

| Disposition         | Count | Meaning                                                                                                                 |
| ------------------- | ----: | ----------------------------------------------------------------------------------------------------------------------- |
| aligned             |     6 | Contract matches a current native/bundled or tracked external route; live configuration/execution still requires proof. |
| contradiction       |     0 | No preserved material skill/schema contradiction remains after architectural correction.                                |
| unverified          |     7 | A current schedule/live-state claim has no scheduler, worker, receipt, or readback proof in checkout.                   |
| not_product_runtime |    14 | Manual/reference guidance; no product-owned executor is claimed or required.                                            |

## Scope and exclusions

### Included (27)

- afternoon-standup - unverified
- estimation-breakdown - not_product_runtime
- web-search - aligned
- canvas - aligned
- vendor-brief - not_product_runtime
- linkedin-post - unverified
- briefing - not_product_runtime
- stackstone-talk-deck - not_product_runtime
- stackstone-branding - not_product_runtime
- video-frames - aligned
- calendar-today - aligned
- calendar-read - aligned
- weekly-planning - unverified
- event-timeline-builder - not_product_runtime
- file-audit - not_product_runtime
- talk-live - not_product_runtime
- calendar-send - unverified
- document-anonymiser - not_product_runtime
- learning - not_product_runtime
- solution-architecture - not_product_runtime
- stackstone-report - not_product_runtime
- weekly-review - unverified
- system-definition - not_product_runtime
- weather - aligned
- vendor-scorecard - not_product_runtime
- daily-plan - unverified
- kombucha - unverified

### Excluded by owner (5)

- skilzvolt-cartoon-storyboard - excluded by explicit owner instruction because it is cartoon-based/cartoon-only; not audited and not a failure.
- stackstone-cartoon-graphic - excluded by explicit owner instruction because it is cartoon-based/cartoon-only; not audited and not a failure.
- skilzvolt-cartoon-shot-prompts - excluded by explicit owner instruction because it is cartoon-based/cartoon-only; not audited and not a failure.
- skilzvolt-cartoon-ideation - excluded by explicit owner instruction because it is cartoon-based/cartoon-only; not audited and not a failure.
- skilzvolt-cartoon-brand-bible - excluded by explicit owner instruction because it is cartoon-based/cartoon-only; not audited and not a failure.

## Evidence boundary

- **Authoritative live source:** current SkilzVolt catalogue revision and version-pinned skills_get bodies fetched for each assignment. Historical audit snapshots are not current truth.
- **SkilzVolt wiring:** extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36. The extension injects metadata and explicitly forbids stale local organisation fallback; its tool is generic owner-only describe/call.
- **Local skill loading:** src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217. These paths load filesystem SKILL.md roots and optional local slash-command frontmatter; they do not install a remote SkilzVolt body as a local command.
- **Native tools:** src/agents/openclaw-tools.ts:108-163,213-218. Canvas, nodes, LinkedIn mirror, web search/fetch and generic cron/task tools are registered, but registration is not live state.
- **Generic exec approval:** `src/infra/outbound/trust-gate.ts:227-295` and the installer’s `exec.run` configuration (`attached_assets/install-forked-openclaw.sh:465-468,501-519`) show the generic exec.run approval/TOTP route. This can cover a calendar-send command when actually invoked through that route; exact-path and live-gate evidence remain unavailable.
- **Claim vs proof:** source references below prove code shape and declared interfaces only. Actual cadence, deployed external scripts, successful executor calls, destination receipts and current readback remain unverified.
- **Absent-module rule:** a missing dedicated worker/module is not itself a contradiction for a procedural/model/manual skill; no dedicated worker is demanded merely from absence.

## Included reconciliation matrix

| Skill                        | Live contract / declared trigger                                                                                                                                                                                                                          | Repository route and proof                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Inputs -> executor -> destination/readback                                                                                                                                                                                                                                                                                                     | Disposition                                                                                                                                                                                                                     |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **afternoon-standup**        | Declared 13:45 afternoon check; read plans/tasks, both calendars, inbox/WhatsApp, CRM, Garmin and recent sent state; update last-seen state and produce a delta/nudge. **Trigger:** declared scheduled run (13:45); owner request.                        | SkilzVolt owner-only catalogue/body; repository has calendar and CRM pollers but no standup worker or current scheduler record [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389; attached_assets/integrations/crm/poll-crm.py:1-27,243-338; src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout]                                                                                                                       | **Input:** workspace markdown feeds and state files named by the live contract<br>**Executor:** model/manual composition; no checked-in standup executor<br>**Destination/readback:** briefing reply plus last-seen state; no readback/receipt available                                                                                       | **unverified**<br>Scheduler, source freshness, worker completion, delivery and state readback are unavailable.                                                                                                                  |
| **estimation-breakdown**     | Manual requirements-to-work-breakdown and risk/complexity/confidence assessment; requires a system definition or architecture first. **Trigger:** owner request / scoping work.                                                                           | No matching OpenClaw module, installer entry, tool schema or scheduled worker; live body is procedural guidance. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217]                                                                                                                                                                                                                                                                                                                         | **Input:** approved system definition, architecture, risk rubric and assumptions<br>**Executor:** model/manual analysis<br>**Destination/readback:** client-facing table/document; no product-owned destination or receipt                                                                                                                     | **not_product_runtime**<br>Artifact template and review/approval handoff are external to this checkout.                                                                                                                         |
| **web-search**               | First check native OpenClaw web search; use configured provider, report route and citations, and fail clearly when unavailable. **Trigger:** owner asks to search/read/verify web.                                                                        | Native conditional web_search registration and provider-specific TypeBox schema; executor validates filters, resolves key, runs provider and returns structured results. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/tools/web-search.ts:148-231,1635-1855; src/agents/openclaw-tools.ts:108-115,213-215; src/agents/tools/web-tools.enabled-defaults.test.ts:19-35,138-183; src/agents/openclaw-tools.ts:108-163,213-218]                                                                                                                                                                                                  | **Input:** query plus optional count, locale, freshness, date and provider-specific filters<br>**Executor:** OpenClaw web_search; API-key presence/configuration is required and was not live-tested<br>**Destination/readback:** structured tool result with URLs/snippets/citations; no external write                                       | **aligned**<br>Live provider config, key availability, current network success and citation receipts were not inspected.                                                                                                        |
| **canvas**                   | Create self-contained HTML, identify an online canvas-capable node, build a bind-mode-correct URL, then present/navigate/eval/snapshot/hide as needed. **Trigger:** owner requests visual/demo/dashboard presentation.                                    | Native canvas tool flattens the action schema, resolves node, invokes gateway canvas commands and sanitizes snapshots; gateway canvas host/auth and node capability tests exist. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/tools/canvas-tool.ts:53-87,93-105,107-210; src/gateway/server.impl.ts:513-616; src/gateway/server.canvas-auth.test.ts:108-375; src/cli/nodes-canvas.ts:10-23; src/agents/openclaw-tools.ts:108-163,213-218]                                                                                                                                                                                    | **Input:** HTML target, explicit node, canvas action and optional snapshot/A2UI arguments<br>**Executor:** OpenClaw canvas to gateway node.invoke to paired node; no live node invocation tested<br>**Destination/readback:** paired node canvas or sanitized snapshot media; no live receipt                                                  | **aligned**<br>Canvas host enablement, paired node availability, bind mode and live delivery remain unverified.                                                                                                                 |
| **vendor-brief** ⚠️          | Manual vendor-facing brief from agreed System Definition/Evaluation Matrix; confirm shortlist, contacts, response/demo format, constraints and disclosures before drafting. **Trigger:** owner requests buy/vendor/RFP brief.                             | No local command, module, schema, installer or scheduler; body is a drafting/review procedure. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | **Input:** approved requirements, evaluation matrix and owner-confirmed procurement decisions<br>**Executor:** model/manual document drafting<br>**Destination/readback:** vendor-facing document; no product-owned send/approval receipt                                                                                                      | **not_product_runtime**<br>External document generation and governed release path are not represented here; scanner warning requires cautious handling.                                                                         |
| **linkedin-post** ⚠️         | Draft owner/Stackstone posts only after loading current brief, content calendar, published/queued posts and ideas; Monday/Wednesday schedule wording and anti-repeat gates apply. **Trigger:** declared Monday/Wednesday draft schedule or owner request. | Repository exposes only owner-only read/capture mirror actions; explicitly no LinkedIn post/message/reaction/comment sending. No scheduler or draft worker is proven. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/tools/linkedin-message-mirror-tool.ts:36-56,119-231,252-307; src/agents/tools/linkedin-message-mirror-tool.test.ts:8-59; src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout]                                                                                                                                                                                 | **Input:** local Stackstone content files and live conversation direction<br>**Executor:** model/manual drafting; mirror can capture/read but cannot publish<br>**Destination/readback:** draft response/local content files; no publish receipt                                                                                               | **unverified**<br>Declared cadence, current source files, draft persistence and owner delivery are unavailable; scanner warning applies.                                                                                        |
| **briefing** ⚠️              | Morning briefing on weekday 06:45/weekend 08:00 combining calendar, inbox, WhatsApp, Stackstone feeds/CRM, plan and health; update last-seen state. **Trigger:** declared morning schedule or owner request.                                              | Current body is procedural/model/manual morning briefing guidance. The tracked AI-briefing integration is a separate weekly RSS to rank to Claude/Tavily news sidecar, not this skill's product-runtime route. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; knowledge/integrations/ai-briefing.md:1-34; attached_assets/integrations/ai-briefing/run.py:1-17,131-260; attached_assets/integrations/ai-briefing/synthesize.py:1-24,233-292; src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout]                                                                                             | **Input:** workspace calendar/inbox/messaging/CRM/health files<br>**Executor:** model/manual composition; weekly RSS sidecar is unrelated and is not a morning-briefing executor<br>**Destination/readback:** briefing reply plus last-seen state; no product-owned receipt                                                                    | **not_product_runtime**<br>No product-owned briefing executor or destination is claimed by this procedural body; do not infer a dedicated worker requirement from the absence of a module. Scanner warning applies.             |
| **stackstone-talk-deck**     | Manual standalone branded HTML deck with navigation, fullscreen/progress and contact/QR slide; save output and present to owner. **Trigger:** owner requests talk/presentation/keynote/deck.                                                              | No deck builder or installer/schema in checkout; canvas can display a produced URL but does not generate the deck. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/tools/canvas-tool.ts:53-87,93-105,107-210; src/gateway/server.impl.ts:513-616; src/gateway/server.canvas-auth.test.ts:108-375; src/cli/nodes-canvas.ts:10-23]                                                                                                                                                                                                                                                                                                | **Input:** talk structure, supplied template/assets and branding rules<br>**Executor:** model/manual HTML authoring<br>**Destination/readback:** declared /mnt/user-data/outputs/ plus owner presentation; no receipt                                                                                                                          | **not_product_runtime**<br>Declared output path, template resources and presentation receipt are external/unverified.                                                                                                           |
| **stackstone-branding**      | Reference-only Stackstone colours, typography, layout, table/docx-js implementation and report/deck styling. **Trigger:** used while drafting Stackstone deliverables.                                                                                    | No runtime skill executor; it is a style reference consumed by other manual skills. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | **Input:** document/deck content and branding reference<br>**Executor:** model/manual formatting<br>**Destination/readback:** downstream document/deck                                                                                                                                                                                         | **not_product_runtime**<br>No product-owned document renderer or style conformance test is present.                                                                                                                             |
| **video-frames** ⚠️          | Use ffmpeg to extract first/timestamp/index frames or short clips; perform the mandatory post-use review. **Trigger:** owner asks for frame/thumbnail/video inspection.                                                                                   | Bundled skill declares ffmpeg requirement and points to tracked scripts/frame.sh; shell script validates input/output and invokes ffmpeg. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; skills/video-frames/SKILL.md:1-50; skills/video-frames/scripts/frame.sh:1-75; src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217]                                                                                                                                                                                                                  | **Input:** video file, optional timestamp/index and output image path<br>**Executor:** bundled script via model/tool execution; ffmpeg install/runtime availability not checked<br>**Destination/readback:** explicit output image path plus tool result; no external write beyond requested file                                              | **aligned**<br>ffmpeg binary, input media and live output/readback were not tested; scanner warning applies.                                                                                                                    |
| **calendar-today**           | Read both Outlook and Google feed files, check staleness, return compact time/title entries, and never write personal calendars. **Trigger:** owner asks todays/tomorrows meetings or conflict check.                                                     | Tracked Microsoft/Google pollers fetch calendar data, poll every 15 minutes and write the named feed files; no model calendar writer is needed for read-only use. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389]                                                                                                                                                                                                                                                | **Input:** OUTLOOK_CALENDAR.md and GOOGLE_CALENDAR.md with freshness markers<br>**Executor:** external pollers plus manual/model read; live service state unavailable<br>**Destination/readback:** owner response (time/title only); source readback is the feed files                                                                         | **aligned**<br>Actual poller installation, feed freshness, event completeness and delivery were not verified.                                                                                                                   |
| **calendar-read**            | Fail closed on dates/weekdays/times; use Outlook then Google source entries, preserve ISO source values and convert Outlook UTC to Europe/London. **Trigger:** any date/time/calendar fact requiring verification.                                        | Same tracked Outlook/Google poller outputs supply the declared source layer; no write path is required. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389]                                                                                                                                                                                                                                                                                                          | **Input:** direct calendar feed entry and freshness marker<br>**Executor:** external pollers plus manual/model reconciliation<br>**Destination/readback:** date/time answer with uncertainty when evidence is stale; no external write                                                                                                         | **aligned**<br>Live source freshness and readback cannot be asserted from checkout.                                                                                                                                             |
| **weekly-planning** ⚠️       | Build weekly focus from prior plan, calendar, tasks, CRM/health; write short WEEK_PLAN.md and ask owner to confirm/refine. **Trigger:** declared weekly planning session.                                                                                 | No tracked weekly-planning worker or current scheduler. Generic cron/task tools exist, but no live job/state is available. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout; attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389]                                                                                                                                                                                      | **Input:** calendar/tasks/CRM/health/previous plan files<br>**Executor:** model/manual planning; optional generic cron creation<br>**Destination/readback:** WEEK_PLAN.md plus owner confirmation; no live readback                                                                                                                            | **unverified**<br>Schedule, file path, owner confirmation and resulting plan state are unverified; scanner warning applies.                                                                                                     |
| **event-timeline-builder**   | Manual evidence-first timeline across email/calendar/transcripts/messaging/web, with source/confidence annotations and sources footer; optional HTML template/helper. **Trigger:** owner asks sequence/precedence/history/timeline.                       | No matching timeline builder, template/helper, installer or schema in tracked repository. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | **Input:** searchable primary records and corroborating sources<br>**Executor:** model/manual research and document construction<br>**Destination/readback:** timeline document/HTML; no product-owned receipt                                                                                                                                 | **not_product_runtime**<br>Referenced bundled resources and multi-source search connectors are external/unverified.                                                                                                             |
| **file-audit** ⚠️            | Manual workspace file/skill audit: classify canonical/supporting/transitional/orphan files, preserve useful content, produce FILE-AUDIT and delete queue only after migration. **Trigger:** owner asks to tidy/audit files.                               | No file-audit executor, command schema or deletion queue worker in checkout; body is a safety procedure. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217]                                                                                                                                                                                                                                                                                                                                 | **Input:** workspace tree, skill/process index and governing files<br>**Executor:** model/manual audit<br>**Destination/readback:** audit/policy/delete-queue files; no product-owned approval receipt                                                                                                                                         | **not_product_runtime**<br>Deletion approval, workspace inventory and post-migration readback are external; scanner warning applies.                                                                                            |
| **talk-live** ⚠️             | Manual live-talk response mode: concise owner-approved live messaging, no tokens/URLs/private identifiers/control paths, with approval boundaries. **Trigger:** owner asks for live-message wording or short reply.                                       | No talk-live module; generic message tool exists, but this body is content/safety guidance and no destination is encoded. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/openclaw-tools.ts:108-163,213-218]                                                                                                                                                                                                                                                                                                                                                                                                                    | **Input:** owner-provided context and target audience<br>**Executor:** model/manual copy; delivery only if separately approved through message route<br>**Destination/readback:** draft or separately addressed message; no live receipt                                                                                                       | **not_product_runtime**<br>Target channel, approval and delivery receipt are not established; scanner warning applies.                                                                                                          |
| **calendar-send**            | Create Outlook/Teams invite only after account/calendar confirmation, attendee confirmation, valid TOTP/open gate, exact temp-file command, output verification and email log. **Trigger:** owner explicitly requests calendar send.                      | Tracked create-event.py writes Graph /me/events, refreshes token and prints event ID/Teams URL. Generic exec.run approval/TOTP can cover a command invoked through that route, but exact invocation and live gate configuration are unverified; absence of per-script TOTP is not treated as a bypass. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; attached_assets/integrations/microsoft/create-event.py:1-37,219-283,286-360; src/infra/outbound/trust-gate.ts:227-295; attached_assets/install-forked-openclaw.sh:465-468,501-519; src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout] | **Input:** confirmed account, title, times, attendees, timezone and TOTP/open gate<br>**Executor:** external Python command through generic exec.run approval/TOTP path if invoked there; not registered as a calendar-specific OpenClaw tool<br>**Destination/readback:** Microsoft Graph calendar; command output is only available readback | **unverified**<br>Exact command path, approval/TOTP/open-gate enforcement, live account/event/log receipts and owner confirmations were not inspected; missing per-script TOTP is not treated as a bypass.                      |
| **document-anonymiser**      | Manual PII replacement preserving formatting/numbers/cross-document consistency, then scan every output and filenames before delivery. **Trigger:** owner asks to anonymise/anonymize/redact documents.                                                   | No tracked anonymise.py or OpenClaw document-anonymisation tool/schema; docx converter is a separate artifact utility only. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; attached_assets/integrations/docx-converter/convert.py (artifact conversion only; no anonymisation contract)]                                                                                                                                                                                                                                                                                                                                                  | **Input:** source docx/xlsx/pdf and explicit PII mapping<br>**Executor:** external/manual script/resource<br>**Destination/readback:** sanitized documents and leak-scan report; no product-owned receipt                                                                                                                                      | **not_product_runtime**<br>Referenced resource, file-type fidelity and PII scan proof are unavailable; no tracked XLSX sample was found.                                                                                        |
| **learning**                 | Turn corrections into durable safeguards: identify root cause, governed home, trigger/handoff/output, implement via supported route, test repeat case and report proof/gaps. **Trigger:** owner correction/repeated failure.                              | SkilzVolt exposes governed proposal/status/diff actions, but no automatic learning mutator or proof that a proposal was approved/current. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217]                                                                                                                                                                                                                                                                                                | **Input:** incident/correction plus live skill/process registry<br>**Executor:** model/manual governed proposal<br>**Destination/readback:** approved skill/process change and verification report; no live approval receipt                                                                                                                   | **not_product_runtime**<br>Approval, deployment and repeat-failure verification are unavailable; do not equate proposal submission with activation.                                                                             |
| **solution-architecture** ⚠️ | Manual architecture assessment: load definition, research current tools/models every engagement, compare lean/balanced/robust options, ADRs, C4 views and recommendation. **Trigger:** owner requests architecture/design options.                        | Native web_search can support research, but no architecture generator, ADR/C4 renderer, installer or runtime route is present. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/tools/web-search.ts:148-231,1635-1855; src/agents/openclaw-tools.ts:108-115,213-215; src/agents/tools/web-tools.enabled-defaults.test.ts:19-35,138-183]                                                                                                                                                                                                                                                                                          | **Input:** system definition, current landscape research, constraints and quality attributes<br>**Executor:** model/manual analysis<br>**Destination/readback:** architecture report/ADRs/views; no product-owned receipt                                                                                                                      | **not_product_runtime**<br>Current web research success, artifact generation and approval are unverified; scanner warning applies.                                                                                              |
| **stackstone-report** ⚠️     | Manual client-report generation from discovery/project context, with branding, source recording, client-perspective gates and follow-up email content. **Trigger:** owner requests client report/options document/proposal.                               | Current body is procedural/model/manual client-report guidance. The tracked Stackstone poller is an unrelated report-delivery sidecar that polls website reports and emails pre-existing branded HTML; it is not this skill's product-runtime route. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; attached_assets/integrations/stackstone/report_poller.py:1-23,34-40,500-703]                                                                                                                                                                                                                                                          | **Input:** project files, transcripts, audience and approved framing<br>**Executor:** model/manual drafting; report-delivery poller is a separate sidecar and does not generate this skill's report<br>**Destination/readback:** client report plus optional email; no generation/readback receipt                                             | **not_product_runtime**<br>No product-owned report-generation executor or destination is claimed by this procedural body; do not infer a dedicated worker requirement from the absence of a generator. Scanner warning applies. |
| **weekly-review** ⚠️         | Friday system/process review across BACKLOG/TASKS/SOUL_PENDING/memory/lessons and relevant skills; patch clear improvements and stage owner decisions. **Trigger:** declared Friday/end-of-week review.                                                   | No tracked weekly-review worker or live schedule; generic skill loader and governed SkilzVolt proposal path do not prove execution. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout]                                                                                                                                                                                                                                                                                                                                                       | **Input:** workspace planning, memory, skill/process and audit files<br>**Executor:** model/manual review and governed proposal<br>**Destination/readback:** updated process files/SOUL_PENDING and owner report; no receipt                                                                                                                   | **unverified**<br>Schedule, file state, approval and post-change verification are unavailable; scanner warning applies.                                                                                                         |
| **system-definition** ⚠️     | Manual requirements-engineering definition: actors/goals, boundary, testable FR/NFR, data shape, MoSCoW, acceptance criteria and open questions. **Trigger:** owner requests spec/requirements/system definition.                                         | No system-definition generator, schema or installer; downstream solution-architecture is also manual. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | **Input:** transcripts, notes, prior summaries and sample input/output files<br>**Executor:** model/manual analysis<br>**Destination/readback:** requirements document and open-question register; no product-owned receipt                                                                                                                    | **not_product_runtime**<br>Sample artifacts, approval and downstream handoff are external; scanner warning applies.                                                                                                             |
| **weather**                  | Use approved no-key wttr.in route with explicit location, select current/forecast format, and use official sources for severe alerts. **Trigger:** owner asks weather/forecast/travel check.                                                              | Bundled skill exactly declares curl requirement and approved endpoint; loader reads bundled SKILL.md and metadata bin requirement. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; skills/weather/SKILL.md:1-116; src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217]                                                                                                                                                                                                                                                                        | **Input:** city/region/airport code<br>**Executor:** curl/manual external read; no key required and no write<br>**Destination/readback:** owner response from returned weather text/JSON; no external write                                                                                                                                    | **aligned**<br>curl availability, endpoint response and current forecast were not live-tested.                                                                                                                                  |
| **vendor-scorecard**         | Manual weighted vendor workbook from brief/responses/demo observations; confirm Must/Should/Could/cost model, keep editable and separate fit from cost. **Trigger:** owner requests vendor scorecard/ranking.                                             | No tracked XLSX workbook, generator, spreadsheet schema or installer found; no product tool can produce/read back the workbook. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36]                                                                                                                                                                                                                                                                                                                                                                                                                                                            | **Input:** sent brief, vendor responses and demo observations<br>**Executor:** model/manual spreadsheet authoring<br>**Destination/readback:** editable workbook and decision review; no receipt                                                                                                                                               | **not_product_runtime**<br>Workbook resource and exact destination/readback are unavailable; no tracked XLSX files were found.                                                                                                  |
| **daily-plan**               | Build PLAN.md around calendar, health, revenue and priorities; avoid reserved poller slots; may create [TODAY] cron nudges and relies on live cron readback. **Trigger:** morning stand-up/briefing, health drift or owner request.                       | Generic OpenClaw cron/task tools are registered, but no daily-plan worker, current cron state or PLAN.md runtime snapshot is available. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout; attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389]                                                                                                                                                                         | **Input:** calendar/tasks/health/CRM/week plan and existing cron state<br>**Executor:** model/manual planning plus optional generic cron calls<br>**Destination/readback:** PLAN.md, [TODAY] cron objects and owner response; no live readback                                                                                                 | **unverified**<br>Actual cron creation/deletion, cleanup and delivery receipts are unverified.                                                                                                                                  |
| **kombucha**                 | Read KOMBUCHA tracker, record batches, create two live reminders (day 12/13 and day 14 failsafe), verify live cron state and fail closed if absent. **Trigger:** new batch, taste/bottle timing or weather-sensitive timing.                              | Generic cron tool exists, but no tracked KOMBUCHA reference, dedicated worker, installer or live cron state is present. [extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36; src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout; skills/weather/SKILL.md:1-116]                                                                                                                                                                                                                                                                                                                                    | **Input:** reference/KOMBUCHA.md, weather and live cron objects<br>**Executor:** model/manual tracker update plus optional generic cron creation<br>**Destination/readback:** tracker and two live reminder objects; no readback/receipt                                                                                                       | **unverified**<br>The contract mandatory reminder chain cannot be proven; tracker dates must not be treated as delivery.                                                                                                        |

**Legend:** ⚠️ means SkilzVolt returned a security warning for the current body; it is not a claim that the body is malicious. Matrix rows intentionally distinguish declared contract from proven runtime activation.

## Per-skill evidence and gaps

### 1. afternoon-standup

- **Pinned identity:** `11ff1d50-40e9-4bed-a56b-1749265d01c2` / version `0eaf1303-f8aa-4704-8208-217e6c7c301e`
- **Current-body contract:** Declared 13:45 afternoon check; read plans/tasks, both calendars, inbox/WhatsApp, CRM, Garmin and recent sent state; update last-seen state and produce a delta/nudge.
- **Declared trigger:** declared scheduled run (13:45); owner request
- **Input/evidence:** workspace markdown feeds and state files named by the live contract
- **Route/executor:** SkilzVolt owner-only catalogue/body; repository has calendar and CRM pollers but no standup worker or current scheduler record model/manual composition; no checked-in standup executor
- **Destination/readback:** briefing reply plus last-seen state; no readback/receipt available
- **Tests inspected:** No standup-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389`; `attached_assets/integrations/crm/poll-crm.py:1-27,243-338`; `src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout`
- **Disposition:** **unverified** - Scheduler, source freshness, worker completion, delivery and state readback are unavailable.

### 2. estimation-breakdown

- **Pinned identity:** `15b8a083-1c77-4397-ba80-cceab2d31b02` / version `1bf429fd-38e8-4bd8-9b97-0dff753087f1`
- **Current-body contract:** Manual requirements-to-work-breakdown and risk/complexity/confidence assessment; requires a system definition or architecture first.
- **Declared trigger:** owner request / scoping work
- **Input/evidence:** approved system definition, architecture, risk rubric and assumptions
- **Route/executor:** No matching OpenClaw module, installer entry, tool schema or scheduled worker; live body is procedural guidance. model/manual analysis
- **Destination/readback:** client-facing table/document; no product-owned destination or receipt
- **Tests inspected:** No skill-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217`
- **Disposition:** **not_product_runtime** - Artifact template and review/approval handoff are external to this checkout.

### 3. web-search

- **Pinned identity:** `18f099d5-6d9a-45e3-a660-93e31d4c994b` / version `42e84be9-3085-4ff7-92d3-50789f62bce6`
- **Current-body contract:** First check native OpenClaw web search; use configured provider, report route and citations, and fail clearly when unavailable.
- **Declared trigger:** owner asks to search/read/verify web
- **Input/evidence:** query plus optional count, locale, freshness, date and provider-specific filters
- **Route/executor:** Native conditional web_search registration and provider-specific TypeBox schema; executor validates filters, resolves key, runs provider and returns structured results. OpenClaw web_search; API-key presence/configuration is required and was not live-tested
- **Destination/readback:** structured tool result with URLs/snippets/citations; no external write
- **Tests inspected:** web-tools.enabled-defaults.test.ts:19-35,138-183; web-search.test.ts and web-search.redirect.test.ts cover provider/redirect behavior.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/tools/web-search.ts:148-231,1635-1855; src/agents/openclaw-tools.ts:108-115,213-215; src/agents/tools/web-tools.enabled-defaults.test.ts:19-35,138-183`; `src/agents/openclaw-tools.ts:108-163,213-218`
- **Disposition:** **aligned** - Live provider config, key availability, current network success and citation receipts were not inspected.

### 4. canvas

- **Pinned identity:** `35772a80-d504-4a4b-b5c1-dc90fa26b398` / version `19264848-f41b-4daa-873f-fe13c234efca`
- **Current-body contract:** Create self-contained HTML, identify an online canvas-capable node, build a bind-mode-correct URL, then present/navigate/eval/snapshot/hide as needed.
- **Declared trigger:** owner requests visual/demo/dashboard presentation
- **Input/evidence:** HTML target, explicit node, canvas action and optional snapshot/A2UI arguments
- **Route/executor:** Native canvas tool flattens the action schema, resolves node, invokes gateway canvas commands and sanitizes snapshots; gateway canvas host/auth and node capability tests exist. OpenClaw canvas to gateway node.invoke to paired node; no live node invocation tested
- **Destination/readback:** paired node canvas or sanitized snapshot media; no live receipt
- **Tests inspected:** server.canvas-auth.test.ts:108-375; android-node.capabilities.live.test.ts:74-103; nodes-media tests cover snapshots.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/tools/canvas-tool.ts:53-87,93-105,107-210; src/gateway/server.impl.ts:513-616; src/gateway/server.canvas-auth.test.ts:108-375; src/cli/nodes-canvas.ts:10-23`; `src/agents/openclaw-tools.ts:108-163,213-218`
- **Disposition:** **aligned** - Canvas host enablement, paired node availability, bind mode and live delivery remain unverified.

### 5. vendor-brief

- **Pinned identity:** `47d88f93-92e8-43f1-814e-27a836b0a84a` / version `90fcc4e0-4358-4a8a-8053-41e36a6218a0`
- **Current-body contract:** Manual vendor-facing brief from agreed System Definition/Evaluation Matrix; confirm shortlist, contacts, response/demo format, constraints and disclosures before drafting.
- **Declared trigger:** owner requests buy/vendor/RFP brief
- **Input/evidence:** approved requirements, evaluation matrix and owner-confirmed procurement decisions
- **Route/executor:** No local command, module, schema, installer or scheduler; body is a drafting/review procedure. model/manual document drafting
- **Destination/readback:** vendor-facing document; no product-owned send/approval receipt
- **Tests inspected:** No skill-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`
- **Disposition:** **not_product_runtime** - External document generation and governed release path are not represented here; scanner warning requires cautious handling. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 6. linkedin-post

- **Pinned identity:** `516dade5-4136-4652-bdd3-47e3612c0ba9` / version `171d668f-4edc-4317-b471-638f1f4ad42d`
- **Current-body contract:** Draft owner/Stackstone posts only after loading current brief, content calendar, published/queued posts and ideas; Monday/Wednesday schedule wording and anti-repeat gates apply.
- **Declared trigger:** declared Monday/Wednesday draft schedule or owner request
- **Input/evidence:** local Stackstone content files and live conversation direction
- **Route/executor:** Repository exposes only owner-only read/capture mirror actions; explicitly no LinkedIn post/message/reaction/comment sending. No scheduler or draft worker is proven. model/manual drafting; mirror can capture/read but cannot publish
- **Destination/readback:** draft response/local content files; no publish receipt
- **Tests inspected:** linkedin-message-mirror-tool.test.ts:8-59 proves fixed read-only action surface.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/tools/linkedin-message-mirror-tool.ts:36-56,119-231,252-307; src/agents/tools/linkedin-message-mirror-tool.test.ts:8-59`; `src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout`
- **Disposition:** **unverified** - Declared cadence, current source files, draft persistence and owner delivery are unavailable; scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 7. briefing

- **Pinned identity:** `588a0083-a1fc-4cf2-a653-d8831230fccc` / version `c0a8a663-69d5-4ae8-8e7e-fcaefe40ab3a`
- **Current-body contract:** Morning briefing on weekday 06:45/weekend 08:00 combining calendar, inbox, WhatsApp, Stackstone feeds/CRM, plan and health; update last-seen state.
- **Declared trigger:** declared morning schedule or owner request
- **Input/evidence:** workspace calendar/inbox/messaging/CRM/health files
- **Route/executor:** Current body is procedural/model/manual morning briefing guidance. The tracked AI-briefing integration is a separate weekly RSS to rank to Claude/Tavily news sidecar, not this skill's product-runtime route. model/manual composition; the weekly RSS sidecar is unrelated and is not a morning-briefing executor
- **Destination/readback:** briefing reply plus last-seen state; no product-owned receipt
- **Tests inspected:** No morning-briefing contract test found; mgmt-bot route is documented in knowledge/integrations/ai-briefing.md:29-34.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `knowledge/integrations/ai-briefing.md:1-34; attached_assets/integrations/ai-briefing/run.py:1-17,131-260; attached_assets/integrations/ai-briefing/synthesize.py:1-24,233-292`; `src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout`
- **Disposition:** **not_product_runtime** - No product-owned briefing executor or destination is claimed by this procedural body; do not infer a dedicated worker requirement from the absence of a module. Scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 8. stackstone-talk-deck

- **Pinned identity:** `6026bb9c-79f2-4671-8777-c100e94c11d3` / version `e499d90e-cc43-4490-a055-52d55f97e3c0`
- **Current-body contract:** Manual standalone branded HTML deck with navigation, fullscreen/progress and contact/QR slide; save output and present to owner.
- **Declared trigger:** owner requests talk/presentation/keynote/deck
- **Input/evidence:** talk structure, supplied template/assets and branding rules
- **Route/executor:** No deck builder or installer/schema in checkout; canvas can display a produced URL but does not generate the deck. model/manual HTML authoring
- **Destination/readback:** declared /mnt/user-data/outputs/ plus owner presentation; no receipt
- **Tests inspected:** No talk-deck repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/tools/canvas-tool.ts:53-87,93-105,107-210; src/gateway/server.impl.ts:513-616; src/gateway/server.canvas-auth.test.ts:108-375; src/cli/nodes-canvas.ts:10-23`
- **Disposition:** **not_product_runtime** - Declared output path, template resources and presentation receipt are external/unverified.

### 9. stackstone-branding

- **Pinned identity:** `625b41be-7aad-4f65-9419-cc4d7eb6acb9` / version `55795e1f-0879-4f08-b957-4283e95d988e`
- **Current-body contract:** Reference-only Stackstone colours, typography, layout, table/docx-js implementation and report/deck styling.
- **Declared trigger:** used while drafting Stackstone deliverables
- **Input/evidence:** document/deck content and branding reference
- **Route/executor:** No runtime skill executor; it is a style reference consumed by other manual skills. model/manual formatting
- **Destination/readback:** downstream document/deck
- **Tests inspected:** No branding-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`
- **Disposition:** **not_product_runtime** - No product-owned document renderer or style conformance test is present.

### 10. video-frames

- **Pinned identity:** `6f824bb6-e31b-4a94-85e1-52cef82f0d21` / version `db2c6896-8811-403a-b3be-6430fc7eff2e`
- **Current-body contract:** Use ffmpeg to extract first/timestamp/index frames or short clips; perform the mandatory post-use review.
- **Declared trigger:** owner asks for frame/thumbnail/video inspection
- **Input/evidence:** video file, optional timestamp/index and output image path
- **Route/executor:** Bundled skill declares ffmpeg requirement and points to tracked scripts/frame.sh; shell script validates input/output and invokes ffmpeg. bundled script via model/tool execution; ffmpeg install/runtime availability not checked
- **Destination/readback:** explicit output image path plus tool result; no external write beyond requested file
- **Tests inspected:** No dedicated script test found; loader metadata path is covered by generic skill loading code.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `skills/video-frames/SKILL.md:1-50; skills/video-frames/scripts/frame.sh:1-75`; `src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217`
- **Disposition:** **aligned** - ffmpeg binary, input media and live output/readback were not tested; scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 11. calendar-today

- **Pinned identity:** `70d52362-dbc4-4029-919e-313b5483453e` / version `e20d3fb9-a6e8-492d-b9f4-269f8ed0f15e`
- **Current-body contract:** Read both Outlook and Google feed files, check staleness, return compact time/title entries, and never write personal calendars.
- **Declared trigger:** owner asks todays/tomorrows meetings or conflict check
- **Input/evidence:** OUTLOOK_CALENDAR.md and GOOGLE_CALENDAR.md with freshness markers
- **Route/executor:** Tracked Microsoft/Google pollers fetch calendar data, poll every 15 minutes and write the named feed files; no model calendar writer is needed for read-only use. external pollers plus manual/model read; live service state unavailable
- **Destination/readback:** owner response (time/title only); source readback is the feed files
- **Tests inspected:** No calendar-today skill-specific test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389`
- **Disposition:** **aligned** - Actual poller installation, feed freshness, event completeness and delivery were not verified.

### 12. calendar-read

- **Pinned identity:** `7b3f4ea0-9b45-4281-b53d-852a2de4de7a` / version `0a2896eb-7f4d-4d23-8b9d-51ebcd2e07b9`
- **Current-body contract:** Fail closed on dates/weekdays/times; use Outlook then Google source entries, preserve ISO source values and convert Outlook UTC to Europe/London.
- **Declared trigger:** any date/time/calendar fact requiring verification
- **Input/evidence:** direct calendar feed entry and freshness marker
- **Route/executor:** Same tracked Outlook/Google poller outputs supply the declared source layer; no write path is required. external pollers plus manual/model reconciliation
- **Destination/readback:** date/time answer with uncertainty when evidence is stale; no external write
- **Tests inspected:** No calendar-read skill-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389`
- **Disposition:** **aligned** - Live source freshness and readback cannot be asserted from checkout.

### 13. weekly-planning

- **Pinned identity:** `818d03ae-e5e8-4021-bc50-797839315628` / version `b838a234-10f4-4bdf-a2b6-98de7832eb6d`
- **Current-body contract:** Build weekly focus from prior plan, calendar, tasks, CRM/health; write short WEEK_PLAN.md and ask owner to confirm/refine.
- **Declared trigger:** declared weekly planning session
- **Input/evidence:** calendar/tasks/CRM/health/previous plan files
- **Route/executor:** No tracked weekly-planning worker or current scheduler. Generic cron/task tools exist, but no live job/state is available. model/manual planning; optional generic cron creation
- **Destination/readback:** WEEK_PLAN.md plus owner confirmation; no live readback
- **Tests inspected:** No weekly-planning-specific test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout`; `attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389`
- **Disposition:** **unverified** - Schedule, file path, owner confirmation and resulting plan state are unverified; scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 14. event-timeline-builder

- **Pinned identity:** `84cc9627-57cb-46a5-85c2-59da46387760` / version `f5d3758b-9d44-4650-b57d-c3f55659ac7d`
- **Current-body contract:** Manual evidence-first timeline across email/calendar/transcripts/messaging/web, with source/confidence annotations and sources footer; optional HTML template/helper.
- **Declared trigger:** owner asks sequence/precedence/history/timeline
- **Input/evidence:** searchable primary records and corroborating sources
- **Route/executor:** No matching timeline builder, template/helper, installer or schema in tracked repository. model/manual research and document construction
- **Destination/readback:** timeline document/HTML; no product-owned receipt
- **Tests inspected:** No timeline-builder repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`
- **Disposition:** **not_product_runtime** - Referenced bundled resources and multi-source search connectors are external/unverified.

### 15. file-audit

- **Pinned identity:** `870bfa4a-80c8-4653-85f9-10afb91022ac` / version `cc37ff18-c6fa-4fa5-ac4c-1263e4f7fad9`
- **Current-body contract:** Manual workspace file/skill audit: classify canonical/supporting/transitional/orphan files, preserve useful content, produce FILE-AUDIT and delete queue only after migration.
- **Declared trigger:** owner asks to tidy/audit files
- **Input/evidence:** workspace tree, skill/process index and governing files
- **Route/executor:** No file-audit executor, command schema or deletion queue worker in checkout; body is a safety procedure. model/manual audit
- **Destination/readback:** audit/policy/delete-queue files; no product-owned approval receipt
- **Tests inspected:** No file-audit-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217`
- **Disposition:** **not_product_runtime** - Deletion approval, workspace inventory and post-migration readback are external; scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 16. talk-live

- **Pinned identity:** `8f56936a-21d1-45e8-a063-ae31bb2c920e` / version `1c6cd645-78cb-403f-bca1-63b5928b0612`
- **Current-body contract:** Manual live-talk response mode: concise owner-approved live messaging, no tokens/URLs/private identifiers/control paths, with approval boundaries.
- **Declared trigger:** owner asks for live-message wording or short reply
- **Input/evidence:** owner-provided context and target audience
- **Route/executor:** No talk-live module; generic message tool exists, but this body is content/safety guidance and no destination is encoded. model/manual copy; delivery only if separately approved through message route
- **Destination/readback:** draft or separately addressed message; no live receipt
- **Tests inspected:** No talk-live-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/openclaw-tools.ts:108-163,213-218`
- **Disposition:** **not_product_runtime** - Target channel, approval and delivery receipt are not established; scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 17. calendar-send

- **Pinned identity:** `93682993-158c-4cc2-9c98-82787fdda8d2` / version `18530eb2-ddb2-4855-b8a0-7ab87542d65a`
- **Current-body contract:** Create Outlook/Teams invite only after account/calendar confirmation, attendee confirmation, valid TOTP/open gate, exact temp-file command, output verification and email log.
- **Declared trigger:** owner explicitly requests calendar send
- **Input/evidence:** confirmed account, title, times, attendees, timezone and TOTP/open gate
- **Route/executor:** Tracked create-event.py writes Graph /me/events, refreshes token and prints event ID/Teams URL. Generic exec.run approval/TOTP can cover a command invoked through that route, but exact invocation and live gate configuration are unverified; absence of per-script TOTP is not treated as a bypass. external Python command through generic exec.run approval/TOTP path if invoked there; not registered as a calendar-specific OpenClaw tool
- **Destination/readback:** Microsoft Graph calendar; command output is only available readback
- **Tests inspected:** No calendar-send contract test found; repository trust-gate/exec-approval coverage is generic, not calendar-send-specific.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `attached_assets/integrations/microsoft/create-event.py:1-37,219-283,286-360`; `src/infra/outbound/trust-gate.ts:227-295; attached_assets/install-forked-openclaw.sh:465-468,501-519`; `src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout`
- **Disposition:** **unverified** - Exact command path, approval/TOTP/open-gate enforcement, live account/event/log receipts and owner confirmations were not inspected; missing per-script TOTP is not treated as a bypass.

### 18. document-anonymiser

- **Pinned identity:** `97488ec2-d65d-41a3-b0e3-857514f9a375` / version `e5790a94-3307-4774-8bdb-7580c4f8400a`
- **Current-body contract:** Manual PII replacement preserving formatting/numbers/cross-document consistency, then scan every output and filenames before delivery.
- **Declared trigger:** owner asks to anonymise/anonymize/redact documents
- **Input/evidence:** source docx/xlsx/pdf and explicit PII mapping
- **Route/executor:** No tracked anonymise.py or OpenClaw document-anonymisation tool/schema; docx converter is a separate artifact utility only. external/manual script/resource
- **Destination/readback:** sanitized documents and leak-scan report; no product-owned receipt
- **Tests inspected:** No anonymiser-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `attached_assets/integrations/docx-converter/convert.py (artifact conversion only; no anonymisation contract)`
- **Disposition:** **not_product_runtime** - Referenced resource, file-type fidelity and PII scan proof are unavailable; no tracked XLSX sample was found.

### 19. learning

- **Pinned identity:** `9a0bdf7a-25da-439f-8896-9da68d222148` / version `d2c98143-2a88-4f9c-9612-9bc7d3080b4b`
- **Current-body contract:** Turn corrections into durable safeguards: identify root cause, governed home, trigger/handoff/output, implement via supported route, test repeat case and report proof/gaps.
- **Declared trigger:** owner correction/repeated failure
- **Input/evidence:** incident/correction plus live skill/process registry
- **Route/executor:** SkilzVolt exposes governed proposal/status/diff actions, but no automatic learning mutator or proof that a proposal was approved/current. model/manual governed proposal
- **Destination/readback:** approved skill/process change and verification report; no live approval receipt
- **Tests inspected:** No learning-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217`
- **Disposition:** **not_product_runtime** - Approval, deployment and repeat-failure verification are unavailable; do not equate proposal submission with activation.

### 20. solution-architecture

- **Pinned identity:** `a1b1d340-9a96-42bd-a9a2-bb34aab501ac` / version `32b9e223-dd95-4d1f-af3c-60484431b290`
- **Current-body contract:** Manual architecture assessment: load definition, research current tools/models every engagement, compare lean/balanced/robust options, ADRs, C4 views and recommendation.
- **Declared trigger:** owner requests architecture/design options
- **Input/evidence:** system definition, current landscape research, constraints and quality attributes
- **Route/executor:** Native web_search can support research, but no architecture generator, ADR/C4 renderer, installer or runtime route is present. model/manual analysis
- **Destination/readback:** architecture report/ADRs/views; no product-owned receipt
- **Tests inspected:** No solution-architecture-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/tools/web-search.ts:148-231,1635-1855; src/agents/openclaw-tools.ts:108-115,213-215; src/agents/tools/web-tools.enabled-defaults.test.ts:19-35,138-183`
- **Disposition:** **not_product_runtime** - Current web research success, artifact generation and approval are unverified; scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 21. stackstone-report

- **Pinned identity:** `ab86a330-ec2c-4545-971d-fda5bda6857b` / version `2601161a-28b0-4611-a766-b4844d134e06`
- **Current-body contract:** Manual client-report generation from discovery/project context, with branding, source recording, client-perspective gates and follow-up email content.
- **Declared trigger:** owner requests client report/options document/proposal
- **Input/evidence:** project files, transcripts, audience and approved framing
- **Route/executor:** Current body is procedural/model/manual client-report guidance. The tracked Stackstone poller is an unrelated report-delivery sidecar that polls website reports and emails pre-existing branded HTML; it is not this skill's product-runtime route. model/manual drafting; report-delivery poller is a separate sidecar and does not generate this skill's report
- **Destination/readback:** client report plus optional email; no generation/readback receipt
- **Tests inspected:** No stackstone-report generation test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `attached_assets/integrations/stackstone/report_poller.py:1-23,34-40,500-703`
- **Disposition:** **not_product_runtime** - No product-owned report-generation executor or destination is claimed by this procedural body; do not infer a dedicated worker requirement from the absence of a generator. Scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 22. weekly-review

- **Pinned identity:** `d07da866-d0ff-4de2-a842-190f82bce305` / version `abf38d9d-f6af-4f59-9bdd-5a8bc09b3c57`
- **Current-body contract:** Friday system/process review across BACKLOG/TASKS/SOUL_PENDING/memory/lessons and relevant skills; patch clear improvements and stage owner decisions.
- **Declared trigger:** declared Friday/end-of-week review
- **Input/evidence:** workspace planning, memory, skill/process and audit files
- **Route/executor:** No tracked weekly-review worker or live schedule; generic skill loader and governed SkilzVolt proposal path do not prove execution. model/manual review and governed proposal
- **Destination/readback:** updated process files/SOUL_PENDING and owner report; no receipt
- **Tests inspected:** No weekly-review-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout`
- **Disposition:** **unverified** - Schedule, file state, approval and post-change verification are unavailable; scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 23. system-definition

- **Pinned identity:** `d997ea47-99f2-4ad0-aeb0-47202f60519e` / version `9dc6cf16-2633-4b00-a96b-80f82b9159f1`
- **Current-body contract:** Manual requirements-engineering definition: actors/goals, boundary, testable FR/NFR, data shape, MoSCoW, acceptance criteria and open questions.
- **Declared trigger:** owner requests spec/requirements/system definition
- **Input/evidence:** transcripts, notes, prior summaries and sample input/output files
- **Route/executor:** No system-definition generator, schema or installer; downstream solution-architecture is also manual. model/manual analysis
- **Destination/readback:** requirements document and open-question register; no product-owned receipt
- **Tests inspected:** No system-definition-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`
- **Disposition:** **not_product_runtime** - Sample artifacts, approval and downstream handoff are external; scanner warning applies. **Security warning:** the live fetch reported a minor scanner concern; use caution and owner review.

### 24. weather

- **Pinned identity:** `e321de40-6741-4cb3-8fea-90df02b21ae6` / version `6d98c676-eb81-4b12-b872-7c7ef8d2e1bc`
- **Current-body contract:** Use approved no-key wttr.in route with explicit location, select current/forecast format, and use official sources for severe alerts.
- **Declared trigger:** owner asks weather/forecast/travel check
- **Input/evidence:** city/region/airport code
- **Route/executor:** Bundled skill exactly declares curl requirement and approved endpoint; loader reads bundled SKILL.md and metadata bin requirement. curl/manual external read; no key required and no write
- **Destination/readback:** owner response from returned weather text/JSON; no external write
- **Tests inspected:** Generic skill loading/eligibility tests cover bundled metadata; no weather-network test run.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `skills/weather/SKILL.md:1-116`; `src/agents/skills/workspace.ts:380-432,445-525,658-687,829-935; src/agents/skills/bundled-dir.ts:36-90; src/agents/skills/frontmatter.ts:208-217`
- **Disposition:** **aligned** - curl availability, endpoint response and current forecast were not live-tested.

### 25. vendor-scorecard

- **Pinned identity:** `e78f1797-f0d6-4146-8493-78ae2a437c0d` / version `48cc44bf-0da7-4841-899b-a15886d6747a`
- **Current-body contract:** Manual weighted vendor workbook from brief/responses/demo observations; confirm Must/Should/Could/cost model, keep editable and separate fit from cost.
- **Declared trigger:** owner requests vendor scorecard/ranking
- **Input/evidence:** sent brief, vendor responses and demo observations
- **Route/executor:** No tracked XLSX workbook, generator, spreadsheet schema or installer found; no product tool can produce/read back the workbook. model/manual spreadsheet authoring
- **Destination/readback:** editable workbook and decision review; no receipt
- **Tests inspected:** No vendor-scorecard repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`
- **Disposition:** **not_product_runtime** - Workbook resource and exact destination/readback are unavailable; no tracked XLSX files were found.

### 26. daily-plan

- **Pinned identity:** `eeaa0aa4-a777-4a0e-bfc5-c84a87082085` / version `fdc891aa-171c-43b6-a828-c4b1178836a7`
- **Current-body contract:** Build PLAN.md around calendar, health, revenue and priorities; avoid reserved poller slots; may create [TODAY] cron nudges and relies on live cron readback.
- **Declared trigger:** morning stand-up/briefing, health drift or owner request
- **Input/evidence:** calendar/tasks/health/CRM/week plan and existing cron state
- **Route/executor:** Generic OpenClaw cron/task tools are registered, but no daily-plan worker, current cron state or PLAN.md runtime snapshot is available. model/manual planning plus optional generic cron calls
- **Destination/readback:** PLAN.md, [TODAY] cron objects and owner response; no live readback
- **Tests inspected:** No daily-plan-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout`; `attached_assets/integrations/microsoft/poll-calendar.py:1-8,67-69,213-245,300-384; attached_assets/integrations/google/poll-calendar-google.py:1-6,38-60,215-229,301-389`
- **Disposition:** **unverified** - Actual cron creation/deletion, cleanup and delivery receipts are unverified.

### 27. kombucha

- **Pinned identity:** `f29e5c40-2cb2-437d-bf05-78dee3f092d3` / version `9dd4d9b0-132b-4e53-9da1-0eda0118878d`
- **Current-body contract:** Read KOMBUCHA tracker, record batches, create two live reminders (day 12/13 and day 14 failsafe), verify live cron state and fail closed if absent.
- **Declared trigger:** new batch, taste/bottle timing or weather-sensitive timing
- **Input/evidence:** reference/KOMBUCHA.md, weather and live cron objects
- **Route/executor:** Generic cron tool exists, but no tracked KOMBUCHA reference, dedicated worker, installer or live cron state is present. model/manual tracker update plus optional generic cron creation
- **Destination/readback:** tracker and two live reminder objects; no readback/receipt
- **Tests inspected:** No kombucha-specific repository test found.
- **Source references:** `extensions/skilzvolt/index.ts:10-15,66-76; extensions/skilzvolt/src/tool.ts:55-93; extensions/skilzvolt/src/client.ts:3-36`; `src/agents/openclaw-tools.ts:149-161; generic scheduler execution has no live state in checkout`; `skills/weather/SKILL.md:1-116`
- **Disposition:** **unverified** - The contract mandatory reminder chain cannot be proven; tracker dates must not be treated as delivery.

## Security warnings

The following current live bodies returned SkilzVolt scanner warnings before content review: `video-frames`, `linkedin-post`, `file-audit`, `talk-live`, `solution-architecture`, `weekly-review`, `briefing`, `weekly-planning`, `vendor-brief`, `stackstone-report`, `system-definition`. The warning text indicated minor scanner concerns and required caution. These rows are not treated as unconditionally trusted; warnings do not by themselves change a disposition.

## Prioritized repairs

1. **P1:** Clarify briefing ownership and keep the weekly RSS sidecar explicitly separate; only add a product-owned route/readback if the briefing contract is intended to be product runtime. Do not infer a dedicated worker from an absent module.
2. **P2:** Verify calendar-send is invoked through the generic exec.run approval/TOTP gate at `src/infra/outbound/trust-gate.ts:227-295` and the installer configuration at `attached_assets/install-forked-openclaw.sh:465-468,501-519`; then verify exact command, account/attendee confirmation and Graph/log readback. Missing per-script TOTP is not itself a bypass.
3. **P3:** For skills that explicitly claim schedules, verify whether product ownership exists via scheduler, execution and delivery observability; do not create dedicated workers solely because no module is tracked.
4. **P4:** Where product runtime is intentionally claimed for manual artifact skills, register approved templates/resources and destination/readback checks (deck, timeline, anonymiser, scorecard, reports); otherwise retain the procedural/manual classification.
5. **P5:** Keep warning-marked skills behind owner review and document scanner findings/mitigations before any writes or external delivery.

## Blockers and non-claims

1. No live scheduler/cron inventory, worker execution state, gateway/node state, destination receipt or external readback was available; therefore cadence and successful delivery are not claimed.
2. Attached integration scripts are repository evidence only. Their deployment, credentials, service installation and current output freshness were not inspected or changed.
3. No live SkilzVolt proposal/mutation, external send, calendar write, LinkedIn publish, file deletion, or skill update was performed.
4. No XLSX files were tracked in the repository; vendor-scorecard remains an external/manual artifact contract, not a proven workbook route.
5. Security warnings were retained as explicit caution markers; no secrets or private body content are reproduced.

## Conclusion

All 27 remaining assigned non-cartoon skills are represented above. Six have a reconciled native/bundled/tracked read or execution route, zero retain a material skill/schema contradiction after correction, seven depend on unverified live scheduling/state (including calendar-send's exact generic exec.run gate path), and fourteen are manual/reference guidance rather than product runtime. The five cartoon skills are excluded by owner instruction and are neither audited nor counted as failures.
