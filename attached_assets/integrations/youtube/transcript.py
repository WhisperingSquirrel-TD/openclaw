#!/usr/bin/env python3
"""
YouTube transcript extractor for OpenClaw.

Fetches captions/transcripts from YouTube videos using youtube-transcript-api.
No API key required — uses YouTube's public caption endpoints.

Usage:
  transcript.py <url_or_id> [--lang LANG] [--raw-json] [--timestamps]

  url_or_id           YouTube URL or video ID
  --lang LANG         Preferred language code (default: en). Falls back to
                      auto-generated captions if manual not available.
  --raw-json          Output raw JSON instead of plain text
  --timestamps        Include timestamps in text output (HH:MM:SS prefix)
  --list-langs        List available transcript languages and exit

Exit codes:
  0  Success
  1  No transcript available (no captions at all)
  2  Video not found or private
  3  Library not installed
"""

import sys
import re
import json
import argparse

def extract_video_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    patterns = [
        r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id):
        return url_or_id
    print(f"Error: Could not extract video ID from: {url_or_id}", file=sys.stderr)
    sys.exit(2)

def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def main():
    parser = argparse.ArgumentParser(description="YouTube transcript extractor")
    parser.add_argument("url_or_id", help="YouTube URL or video ID")
    parser.add_argument("--lang", default="en", help="Preferred language code (default: en)")
    parser.add_argument("--raw-json", action="store_true", help="Output raw JSON")
    parser.add_argument("--timestamps", action="store_true", help="Include timestamps")
    parser.add_argument("--list-langs", action="store_true", help="List available languages")
    args = parser.parse_args()

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("Error: youtube-transcript-api not installed.", file=sys.stderr)
        print("Install: pip3 install --break-system-packages youtube-transcript-api", file=sys.stderr)
        sys.exit(3)

    video_id = extract_video_id(args.url_or_id)

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except Exception as e:
        err_str = str(e).lower()
        if "could not retrieve" in err_str or "no transcripts" in err_str:
            print(f"Error: No transcripts available for video {video_id}", file=sys.stderr)
            print("This video has no captions (manual or auto-generated).", file=sys.stderr)
            sys.exit(1)
        if "video unavailable" in err_str or "private" in err_str:
            print(f"Error: Video {video_id} is unavailable or private", file=sys.stderr)
            sys.exit(2)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.list_langs:
        langs = []
        for t in transcript_list:
            langs.append({
                "language": t.language,
                "language_code": t.language_code,
                "is_generated": t.is_generated,
                "is_translatable": t.is_translatable,
            })
        if args.raw_json:
            print(json.dumps(langs, indent=2))
        else:
            print(f"Available transcripts for {video_id}:")
            for lang in langs:
                gen = " (auto-generated)" if lang["is_generated"] else " (manual)"
                print(f"  {lang['language_code']}: {lang['language']}{gen}")
        return

    transcript = None
    source_info = ""

    try:
        t = transcript_list.find_transcript([args.lang])
        transcript = t.fetch()
        source_info = f"manual ({t.language_code})" if not t.is_generated else f"auto-generated ({t.language_code})"
    except Exception:
        try:
            t = transcript_list.find_generated_transcript([args.lang])
            transcript = t.fetch()
            source_info = f"auto-generated ({t.language_code})"
        except Exception:
            try:
                for t in transcript_list:
                    transcript = t.fetch()
                    source_info = f"{'auto-generated' if t.is_generated else 'manual'} ({t.language_code})"
                    break
            except Exception:
                pass

    if not transcript:
        print(f"Error: Could not fetch transcript for video {video_id}", file=sys.stderr)
        sys.exit(1)

    if args.raw_json:
        output = {
            "video_id": video_id,
            "source": source_info,
            "segments": len(transcript),
            "transcript": transcript,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    print(f"# Transcript: {video_id}")
    print(f"# Source: {source_info}")
    print(f"# Segments: {len(transcript)}")
    print()

    if args.timestamps:
        for entry in transcript:
            ts = format_timestamp(entry.get("start", 0))
            text = entry.get("text", "").strip()
            if text:
                print(f"[{ts}] {text}")
    else:
        parts = []
        for entry in transcript:
            text = entry.get("text", "").strip()
            if text:
                parts.append(text)
        print(" ".join(parts))

if __name__ == "__main__":
    main()
