#!/usr/bin/env bash
set -euo pipefail

# Offline regression coverage for transcribe.sh. The fake curl is placed first
# on PATH, so no test case can contact api.openai.com or use a real credential.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SCRIPT_DIR}/transcribe.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

fake_bin="${tmp}/bin"
mkdir -p "$fake_bin"
cat >"${fake_bin}/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >"${CURL_LOG:?}"
if [[ "${CURL_MODE:-success}" == "error" ]]; then
  echo "fixture API failure" >&2
  exit 22
fi
printf '%s' "${CURL_RESPONSE:-fixture transcript}"
EOF
chmod +x "${fake_bin}/curl"

audio="${tmp}/meeting.ogg"
printf 'not real audio; only the fixture path is exercised\n' >"$audio"

if env -u OPENAI_API_KEY PATH="${fake_bin}:$PATH" bash "$SCRIPT" "${tmp}/missing.ogg" \
  >"${tmp}/missing.stdout" 2>"${tmp}/missing.stderr"; then
  fail "missing audio should fail"
fi
grep -Fq "File not found" "${tmp}/missing.stderr" || fail "missing-file error was not reported"

if env -u OPENAI_API_KEY PATH="${fake_bin}:$PATH" bash "$SCRIPT" "$audio" \
  >"${tmp}/key.stdout" 2>"${tmp}/key.stderr"; then
  fail "missing API key should fail"
fi
grep -Fq "Missing OPENAI_API_KEY" "${tmp}/key.stderr" || fail "missing-key error was not reported"

curl_log="${tmp}/curl.log"
OPENAI_API_KEY="whisper-test-key" \
  CURL_LOG="$curl_log" \
  PATH="${fake_bin}:$PATH" \
  bash "$SCRIPT" "$audio" --model whisper-test --language en --prompt "Speaker: Test" \
  >"${tmp}/success.stdout"

[[ "$(cat "${tmp}/success.stdout")" == "${audio%.ogg}.txt" ]] ||
  fail "default output path was not printed"
[[ "$(cat "${audio%.ogg}.txt")" == "fixture transcript" ]] ||
  fail "fixture transcript was not written"
grep -Fq -- "https://api.openai.com/v1/audio/transcriptions" "$curl_log" ||
  fail "the transcription endpoint was not selected"
grep -Fq -- "-H Authorization: Bearer whisper-test-key" "$curl_log" ||
  fail "the authorization header was not passed"
grep -Fq -- "-F model=whisper-test" "$curl_log" || fail "model option was not passed"
grep -Fq -- "-F language=en" "$curl_log" || fail "language option was not passed"
grep -Fq -- "-F prompt=Speaker: Test" "$curl_log" || fail "prompt option was not passed"

json_out="${tmp}/nested/meeting.json"
OPENAI_API_KEY="whisper-test-key" \
  CURL_LOG="$curl_log" \
  CURL_RESPONSE='{"text":"json fixture"}' \
  PATH="${fake_bin}:$PATH" \
  bash "$SCRIPT" "$audio" --json --out "$json_out" >"${tmp}/json.stdout"
[[ "$(cat "${tmp}/json.stdout")" == "$json_out" ]] || fail "explicit output path was not printed"
[[ "$(cat "$json_out")" == '{"text":"json fixture"}' ]] || fail "JSON fixture was not written"
grep -Fq -- "-F response_format=json" "$curl_log" || fail "JSON response format was not passed"

if OPENAI_API_KEY="whisper-test-key" \
  CURL_LOG="$curl_log" \
  CURL_MODE=error \
  PATH="${fake_bin}:$PATH" \
  bash "$SCRIPT" "$audio" --out "${tmp}/failed.txt" \
  >"${tmp}/failure.stdout" 2>"${tmp}/failure.stderr"; then
  fail "curl failure should preserve a non-zero exit"
fi
grep -Fq "fixture API failure" "${tmp}/failure.stderr" ||
  fail "curl failure was not visible to the caller"

if PATH="${fake_bin}:$PATH" bash "$SCRIPT" "$audio" --unknown \
  >"${tmp}/arg.stdout" 2>"${tmp}/arg.stderr"; then
  fail "unknown arguments should fail"
fi
grep -Fq "Unknown arg: --unknown" "${tmp}/arg.stderr" ||
  fail "unknown-argument error was not reported"

echo "transcribe.sh offline tests passed"