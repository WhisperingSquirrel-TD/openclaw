#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from integrations.ai_briefing_service_client import AIBriefingServiceClient


def emit(resp):
    print(json.dumps(resp.payload, indent=2))


def main() -> None:
    client = AIBriefingServiceClient()
    parser = argparse.ArgumentParser(description="OpenClaw-side control bridge for AI Briefing Outbound Service")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("list-runs")

    c = sub.add_parser("create-run")
    c.add_argument("--name", required=True)
    c.add_argument("--mode", default="generate_only")
    c.add_argument("--notes")

    rs = sub.add_parser("run-summary")
    rs.add_argument("--run-id", type=int, required=True)

    wr = sub.add_parser("watch-run")
    wr.add_argument("--run-id", type=int, required=True)

    mr = sub.add_parser("mark-run-for-prepare")
    mr.add_argument("--run-id", type=int, required=True)

    cp = sub.add_parser("preview-crm-targets")
    cp.add_argument("--limit", type=int)

    ci = sub.add_parser("import-crm-targets")
    ci.add_argument("--limit", type=int)
    ci.add_argument("--force-regenerate", action="store_true")
    ci.add_argument("--run-id", type=int)
    ci.add_argument("--post-generation-action", default="generate_only")

    at = sub.add_parser("add-target")
    at.add_argument("--crm-id", required=True)
    at.add_argument("--company-name", required=True)
    at.add_argument("--website-url", required=True)
    at.add_argument("--contact-email", required=True)
    at.add_argument("--contact-name")
    at.add_argument("--campaign-segment")
    at.add_argument("--force-regenerate", action="store_true")
    at.add_argument("--run-id", type=int)
    at.add_argument("--post-generation-action", default="generate_only")

    lb = sub.add_parser("list-briefings")
    lb.add_argument("--run-id", type=int)

    sb = sub.add_parser("submit-briefings")
    sb.add_argument("--run-id", type=int)

    pb = sub.add_parser("poll-briefings")
    pb.add_argument("--run-id", type=int)
    pb.add_argument("--once", action="store_true")
    pb.add_argument("--until-run-complete", action="store_true")

    sub.add_parser("list-send-packs")

    rc = sub.add_parser("review-card")
    rc.add_argument("--send-pack-id", type=int, required=True)

    bsp = sub.add_parser("build-send-packs")
    bsp.add_argument("--run-id", type=int)
    bsp.add_argument("--include-generate-only", action="store_true")

    vsp = sub.add_parser("validate-send-pack")
    vsp.add_argument("--send-pack-id", type=int, required=True)

    vob = sub.add_parser("verify-outbound")
    vob.add_argument("--send-pack-id", type=int, required=True)

    asp = sub.add_parser("approve-send-pack")
    asp.add_argument("--send-pack-id", type=int, required=True)

    sub.add_parser("list-outbound")

    ss = sub.add_parser("schedule-send")
    ss.add_argument("--send-pack-id", type=int, required=True)
    ss.add_argument("--scheduled-send-at", required=True)

    rsq = sub.add_parser("run-send-queue")
    rsq.add_argument("--execute", action="store_true")
    rsq.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()

    cmd = args.command
    if cmd == "health":
        emit(client.health())
    elif cmd == "list-runs":
        emit(client.list_runs())
    elif cmd == "create-run":
        emit(client.create_run(args.name, args.mode, args.notes))
    elif cmd == "run-summary":
        emit(client.run_summary(args.run_id))
    elif cmd == "watch-run":
        emit(client.watch_run(args.run_id))
    elif cmd == "mark-run-for-prepare":
        emit(client.mark_run_for_prepare(args.run_id))
    elif cmd == "preview-crm-targets":
        emit(client.preview_crm_targets(args.limit))
    elif cmd == "import-crm-targets":
        emit(client.import_crm_targets(args.limit, args.force_regenerate, args.run_id, args.post_generation_action))
    elif cmd == "add-target":
        emit(client.add_target(args.crm_id, args.company_name, args.website_url, args.contact_email, args.contact_name, args.campaign_segment, args.force_regenerate, args.run_id, args.post_generation_action))
    elif cmd == "list-briefings":
        emit(client.list_briefings(args.run_id))
    elif cmd == "submit-briefings":
        emit(client.submit_briefings(args.run_id))
    elif cmd == "poll-briefings":
        emit(client.poll_briefings(args.once, args.run_id, args.until_run_complete))
    elif cmd == "list-send-packs":
        emit(client.list_send_packs())
    elif cmd == "review-card":
        emit(client.send_pack_review_card(args.send_pack_id))
    elif cmd == "build-send-packs":
        emit(client.build_send_packs(args.run_id, args.include_generate_only))
    elif cmd == "validate-send-pack":
        emit(client.validate_send_pack(args.send_pack_id))
    elif cmd == "verify-outbound":
        emit(client.verify_outbound(args.send_pack_id))
    elif cmd == "approve-send-pack":
        emit(client.approve_send_pack(args.send_pack_id))
    elif cmd == "list-outbound":
        emit(client.list_outbound())
    elif cmd == "schedule-send":
        emit(client.schedule_send(args.send_pack_id, args.scheduled_send_at))
    elif cmd == "run-send-queue":
        emit(client.run_send_queue(args.execute, args.limit))
    else:
        raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
