import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_linkedin_messages.py"
spec = importlib.util.spec_from_file_location("capture_linkedin_messages", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # type: ignore[union-attr]


def test_body_preview_truncates_and_squashes_space():
    text = "hello\n\nworld   " + "x" * 300
    preview = module.body_preview(text, max_chars=20)
    assert preview == "hello world xxxxxxx…"
    assert len(preview) == 20


def test_normalize_thread_generates_stable_keys_and_message_preview():
    raw = {
        "thread_url": "https://www.linkedin.com/messaging/thread/abc/",
        "participant_names": ["Jane Example"],
        "latest_timestamp_text": "10:31",
        "latest_preview": "Hi Tom, useful to speak yesterday.",
    }
    first = module.normalize_thread(raw)
    second = module.normalize_thread(raw)
    assert first["thread_key"] == second["thread_key"]
    assert first["participants"][0]["name"] == "Jane Example"
    assert first["messages"][0]["direction"] == "unknown"
    assert first["messages"][0]["body_hash"].startswith("sha256:")


def test_snapshot_to_markdown_reports_blocker():
    snapshot = module.make_empty_snapshot("login_required", "LinkedIn login required")
    md = module.snapshot_to_markdown(snapshot)
    assert "Coverage state: `login_required`" in md
    assert "Blocker: LinkedIn login required" in md
    assert "No LinkedIn message threads captured" in md


class _ReadyPage:
    frames = []

    def __init__(self):
        self.load_calls = []
        self.function_calls = []

    def wait_for_load_state(self, state, timeout):
        self.load_calls.append((state, timeout))

    def wait_for_function(self, expression, timeout):
        self.function_calls.append((expression, timeout))

    def evaluate(self, expression):
        return {"url": "https://www.linkedin.com/messaging/", "title": "LinkedIn", "ready_state": "complete", "html_chars": 100, "body_html_chars": 50, "message_item_count": 1, "thread_anchor_count": 0, "body_text_chars": 20, "body_text_sample": "Jane Example"}


def test_wait_for_message_document_requires_a_real_document_before_extracting():
    page = _ReadyPage()
    diagnostics = module.wait_for_message_document(page, 30_000)
    assert diagnostics["document_ready"] is True
    assert page.load_calls == [("domcontentloaded", 10_000)]
    assert page.function_calls
    assert diagnostics["body_text_chars"] == 20


class _BlankPage(_ReadyPage):
    def wait_for_load_state(self, state, timeout):
        raise TimeoutError("still loading")

    def wait_for_function(self, expression, timeout):
        raise TimeoutError("blank document")


def test_wait_for_message_document_preserves_blank_page_as_not_ready():
    diagnostics = module.wait_for_message_document(_BlankPage(), 30_000)
    assert diagnostics["document_ready"] is False
    assert "readiness_error" in diagnostics


class _BootstrapPage(_ReadyPage):
    url = "https://www.linkedin.com/messaging/"

    def __init__(self):
        super().__init__()
        self.gotos = []

    def goto(self, url, wait_until, timeout):
        self.gotos.append((url, wait_until, timeout))
        self.url = url


def test_bootstrap_messaging_via_feed_uses_read_only_feed_then_messaging_route():
    page = _BootstrapPage()
    diagnostics = module.bootstrap_messaging_via_feed(page, 30_000)
    assert [item[0] for item in page.gotos] == ["https://www.linkedin.com/feed/", module.LINKEDIN_MESSAGES_URL]
    assert diagnostics["recovery_route"] == "feed_then_messaging"
