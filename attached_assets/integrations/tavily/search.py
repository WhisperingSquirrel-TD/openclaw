#!/usr/bin/env python3
"""
Tavily web search for OpenClaw.

Performs web searches using the Tavily API and returns structured results.
Reads TAVILY_API_KEY from ~/.openclaw/.env.

Usage:
  search.py <query> [--max-results N] [--include-answer] [--search-depth basic|advanced]

  query               The search query string
  --max-results N     Number of results to return (default: 5, max: 20)
  --include-answer    Include an AI-generated answer summary
  --search-depth      "basic" (fast) or "advanced" (thorough, default: basic)
  --raw-json          Output raw JSON instead of formatted text
  --topic general|news  Search topic (default: general)

Exit codes:
  0  Success
  1  API key missing or auth error
  2  Search error
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests


def load_api_key() -> str:
    env_file = Path.home() / ".openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("TAVILY_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")

    key = os.environ.get("TAVILY_API_KEY", "")
    if key:
        return key

    print("ERROR: TAVILY_API_KEY not found in ~/.openclaw/.env or environment", file=sys.stderr)
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenClaw Tavily web search")
    p.add_argument("query", help="Search query")
    p.add_argument("--max-results", type=int, default=5,
                   help="Number of results (default: 5, max: 20)")
    p.add_argument("--include-answer", action="store_true",
                   help="Include AI-generated answer summary")
    p.add_argument("--search-depth", default="basic", choices=["basic", "advanced"],
                   help="Search depth (default: basic)")
    p.add_argument("--raw-json", action="store_true",
                   help="Output raw JSON instead of formatted text")
    p.add_argument("--topic", default="general", choices=["general", "news"],
                   help="Search topic (default: general)")
    return p.parse_args()


def search(api_key: str, query: str, max_results: int = 5,
           include_answer: bool = False, search_depth: str = "basic",
           topic: str = "general") -> dict:
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": min(max_results, 20),
            "include_answer": include_answer,
            "search_depth": search_depth,
            "topic": topic,
        },
        timeout=30,
    )
    if resp.status_code == 401:
        print("ERROR: Invalid TAVILY_API_KEY", file=sys.stderr)
        sys.exit(1)
    if not resp.ok:
        print(f"Search failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(2)
    return resp.json()


def format_results(data: dict) -> str:
    lines = []
    answer = data.get("answer")
    if answer:
        lines.append(f"Answer: {answer}")
        lines.append("")

    results = data.get("results", [])
    if not results:
        lines.append("No results found.")
        return "\n".join(lines)

    for i, r in enumerate(results, 1):
        title = r.get("title", "(no title)")
        url = r.get("url", "")
        content = r.get("content", "")
        lines.append(f"[{i}] {title}")
        lines.append(f"    {url}")
        if content:
            lines.append(f"    {content[:500]}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    api_key = load_api_key()
    data = search(
        api_key=api_key,
        query=args.query,
        max_results=args.max_results,
        include_answer=args.include_answer,
        search_depth=args.search_depth,
        topic=args.topic,
    )
    if args.raw_json:
        print(json.dumps(data, indent=2))
    else:
        print(format_results(data))


if __name__ == "__main__":
    main()
