"""Offline contract tests for the Google poller authentication routes.

These tests never contact Google and never read a real token.  The poller
modules are loaded with small dependency stubs so the OAuth contract can be
tested on a development machine without installing the Google client stack.
"""

from __future__ import annotations

import importlib.util
import base64
import hashlib
import json
import os
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit


GOOGLE_DIR = Path(__file__).parent


try:
    import requests
    from google_auth_oauthlib.flow import InstalledAppFlow as RealInstalledAppFlow

    REAL_OAUTH_LIBRARIES_AVAILABLE = True
except ImportError:
    requests = None
    RealInstalledAppFlow = None
    REAL_OAUTH_LIBRARIES_AVAILABLE = False


def _install_google_stubs() -> None:
    """Install just enough modules for importing either poller offline."""

    google = types.ModuleType("google")
    oauth2 = types.ModuleType("google.oauth2")
    credentials = types.ModuleType("google.oauth2.credentials")
    auth = types.ModuleType("google.auth")
    transport = types.ModuleType("google.auth.transport")
    requests = types.ModuleType("google.auth.transport.requests")
    oauthlib = types.ModuleType("google_auth_oauthlib")
    flow = types.ModuleType("google_auth_oauthlib.flow")
    apiclient = types.ModuleType("googleapiclient")
    discovery = types.ModuleType("googleapiclient.discovery")

    class Credentials:
        @classmethod
        def from_authorized_user_file(cls, *_args, **_kwargs):
            raise AssertionError("offline tests must not read a token")

    class Request:
        pass

    class InstalledAppFlow:
        @classmethod
        def from_client_secrets_file(cls, *_args, **_kwargs):
            raise AssertionError("offline tests must provide a fake flow")

    credentials.Credentials = Credentials
    requests.Request = Request
    flow.InstalledAppFlow = InstalledAppFlow
    discovery.build = lambda *_args, **_kwargs: None

    google.oauth2 = oauth2
    google.auth = auth
    oauth2.credentials = credentials
    auth.transport = transport
    transport.requests = requests
    oauthlib.flow = flow
    apiclient.discovery = discovery

    for name, module in (
        ("google", google),
        ("google.oauth2", oauth2),
        ("google.oauth2.credentials", credentials),
        ("google.auth", auth),
        ("google.auth.transport", transport),
        ("google.auth.transport.requests", requests),
        ("google_auth_oauthlib", oauthlib),
        ("google_auth_oauthlib.flow", flow),
        ("googleapiclient", apiclient),
        ("googleapiclient.discovery", discovery),
    ):
        sys.modules[name] = module


def _load_poller(filename: str, module_name: str):
    _install_google_stubs()
    spec = importlib.util.spec_from_file_location(module_name, GOOGLE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_poller_with_real_oauth(filename: str, module_name: str):
    """Load a poller with real OAuth libraries and only a discovery stub."""

    for name in list(sys.modules):
        if (
            name == "google"
            or name.startswith("google.")
            or name == "google_auth_oauthlib"
            or name.startswith("google_auth_oauthlib.")
            or name == "oauthlib"
            or name.startswith("oauthlib.")
            or name == "requests_oauthlib"
            or name.startswith("requests_oauthlib.")
        ):
            del sys.modules[name]

    apiclient = types.ModuleType("googleapiclient")
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda *_args, **_kwargs: None
    apiclient.discovery = discovery
    sys.modules["googleapiclient"] = apiclient
    sys.modules["googleapiclient.discovery"] = discovery

    spec = importlib.util.spec_from_file_location(module_name, GOOGLE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class FakeCredentials:
    refresh_token = "offline-refresh-token"

    def to_json(self) -> str:
        return '{"access_token":"offline-test-only"}'


class FakeFlow:
    def __init__(self) -> None:
        self.credentials = FakeCredentials()
        self.authorization_calls: list[dict] = []
        self.authorization_url_value: str | None = None
        self.callback: str | None = None

    def authorization_url(self, **kwargs):
        self.authorization_calls.append(kwargs)
        query = urlencode({"state": "state-123", **kwargs})
        self.authorization_url_value = f"https://accounts.google.com/o/oauth2/auth?{query}"
        return self.authorization_url_value, "state-123"

    def fetch_token(self, **kwargs):
        self.callback = kwargs["authorization_response"]


class GoogleAuthContractTests(TestCase):
    def test_phone_callback_requires_exact_localhost_redirect(self) -> None:
        poller = _load_poller("poll-calendar-google.py", "google_calendar_poller_test")

        poller._validate_callback_url(
            "http://localhost:8765/?code=offline-code&state=state-123",
            "state-123",
        )

        for callback in (
            "https://localhost:8765/?code=offline-code&state=state-123",
            "http://127.0.0.1:8765/?code=offline-code&state=state-123",
            "http://localhost:9999/?code=offline-code&state=state-123",
            "http://localhost:8765/?code=offline-code&state=wrong-state",
            "http://localhost:8765/?error=access_denied&state=state-123",
        ):
            with self.subTest(callback=callback), self.assertRaises(ValueError):
                poller._validate_callback_url(callback, "state-123")

    def test_phone_auth_uses_standard_authorization_and_full_callback(self) -> None:
        poller = _load_poller("poll-calendar-google.py", "google_calendar_poller_flow_test")
        fake_flow = FakeFlow()
        callback = "http://localhost:8765/?code=offline-code&state=state-123"
        output: list[str] = []

        credentials = poller._complete_phone_auth(
            fake_flow,
            read_callback=lambda _prompt: callback,
            write_output=output.append,
        )

        self.assertIs(credentials, fake_flow.credentials)
        self.assertEqual(
            fake_flow.callback,
            "https://localhost:8765/?code=offline-code&state=state-123",
        )
        self.assertEqual(
            fake_flow.authorization_calls,
            [{"access_type": "offline", "prompt": "consent"}],
        )
        self.assertEqual(
            parse_qs(urlsplit(fake_flow.authorization_url_value).query),
            {
                "state": ["state-123"],
                "access_type": ["offline"],
                "prompt": ["consent"],
            },
        )
        self.assertTrue(any("accounts.google.com" in line for line in output))
        self.assertNotIn("offline-code", "\n".join(output))

    def test_oauthlib_callback_rewrite_happens_only_after_validation(self) -> None:
        poller = _load_poller("poll-calendar-google.py", "google_calendar_poller_parser_test")
        callback = "http://localhost:8765/?code=offline-code&state=state-123"

        self.assertEqual(
            poller._oauthlib_authorization_response(callback, "state-123"),
            "https://localhost:8765/?code=offline-code&state=state-123",
        )
        with self.assertRaises(ValueError):
            poller._oauthlib_authorization_response(
                "http://localhost:8765/?code=offline-code&state=wrong-state",
                "state-123",
            )

    def test_token_write_is_private_and_atomic_enough_for_readback(self) -> None:
        poller = _load_poller("poll-calendar-google.py", "google_calendar_poller_write_test")

        with TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "token.json"
            poller._write_token_file(token_path, FakeCredentials())

            self.assertEqual(token_path.read_text(), '{"access_token":"offline-test-only"}')
            self.assertEqual(os.stat(token_path).st_mode & 0o777, 0o600)

    def test_auth_failure_does_not_delete_existing_token(self) -> None:
        poller = _load_poller("poll-calendar-google.py", "google_calendar_poller_failure_test")

        with TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "token.json"
            token_path.write_text('{"existing":"token"}')
            credentials_path = Path(temp_dir) / "credentials.json"
            credentials_path.write_text("{}")
            poller.TOKEN_FILE = token_path
            poller.CREDENTIALS_FILE = credentials_path
            output: list[str] = []

            with patch.object(
                poller.InstalledAppFlow,
                "from_client_secrets_file",
                return_value=FakeFlowThatFails(),
            ) as from_client_secrets_file, self.assertRaises(SystemExit):
                poller.do_auth(
                    read_callback=lambda _prompt: (
                        "http://localhost:8765/?code=offline-code&state=state-123"
                    ),
                    write_output=output.append,
                )

            from_client_secrets_file.assert_called_once_with(
                str(credentials_path),
                poller.SCOPES,
                autogenerate_code_verifier=True,
            )
            self.assertEqual(token_path.read_text(), '{"existing":"token"}')
            self.assertNotIn("offline-code", "\n".join(output))

    def test_auth_flows_explicitly_autogenerate_pkce_verifiers(self) -> None:
        for filename, credentials_name, token_name in (
            (
                "poll-calendar-google.py",
                "credentials.json",
                "token.json",
            ),
            ("gmail_poll.py", "gmail-credentials.json", "gmail-token.json"),
        ):
            with self.subTest(filename=filename):
                poller = _load_poller(filename, f"google_pkce_constructor_{filename}")
                with TemporaryDirectory() as temp_dir:
                    credentials_path = Path(temp_dir) / credentials_name
                    credentials_path.write_text("{}")
                    poller.CREDENTIALS_FILE = credentials_path
                    poller.TOKEN_FILE = Path(temp_dir) / token_name

                    with patch.object(
                        poller.InstalledAppFlow,
                        "from_client_secrets_file",
                        return_value=FakeFlow(),
                    ) as from_client_secrets_file, patch.object(
                        poller,
                        "_complete_phone_auth",
                        return_value=FakeCredentials(),
                    ), patch.object(poller, "_write_token_file"), patch.object(
                        poller, "log"
                    ):
                        poller.do_auth(write_output=lambda _line: None)

                    from_client_secrets_file.assert_called_once_with(
                        str(credentials_path),
                        poller.SCOPES,
                        autogenerate_code_verifier=True,
                    )

    def test_auth_rejects_non_refreshable_replacement(self) -> None:
        for filename, credentials_name, token_name, port in (
            (
                "poll-calendar-google.py",
                "credentials.json",
                "token.json",
                8765,
            ),
            ("gmail_poll.py", "gmail-credentials.json", "gmail-token.json", 8766),
        ):
            with self.subTest(filename=filename):
                poller = _load_poller(filename, f"google_no_refresh_replacement_{filename}")
                with TemporaryDirectory() as temp_dir:
                    credentials_path = Path(temp_dir) / credentials_name
                    credentials_path.write_text("{}")
                    token_path = Path(temp_dir) / token_name
                    token_path.write_text('{"existing":"token"}')
                    poller.CREDENTIALS_FILE = credentials_path
                    poller.TOKEN_FILE = token_path
                    output: list[str] = []

                    with patch.object(
                        poller.InstalledAppFlow,
                        "from_client_secrets_file",
                        return_value=FakeFlowWithoutRefresh(),
                    ), patch.object(poller, "log"), self.assertRaises(SystemExit):
                        poller.do_auth(
                            read_callback=lambda _prompt: (
                                f"http://localhost:{port}/?code=offline-code&state=state-123"
                            ),
                            write_output=output.append,
                        )

                    self.assertEqual(token_path.read_text(), '{"existing":"token"}')
                    self.assertNotIn("offline-code", "\n".join(output))

    def test_gmail_service_does_not_start_interactive_oauth_without_a_tty(self) -> None:
        poller = _load_poller("gmail_poll.py", "gmail_poller_noninteractive_test")
        with TemporaryDirectory() as temp_dir:
            poller.TOKEN_FILE = Path(temp_dir) / "gmail-token.json"
            poller.CREDENTIALS_FILE = Path(temp_dir) / "gmail-credentials.json"
            poller.CREDENTIALS_FILE.write_text("{}")

            with patch.object(poller.sys.stdin, "isatty", return_value=False), patch.object(
                poller, "log"
            ) as log:
                self.assertIsNone(poller.get_service())

        messages = "\n".join(call.args[0] for call in log.call_args_list)
        self.assertIn("--auth", messages)

    def test_gmail_phone_auth_uses_a_distinct_loopback_port(self) -> None:
        poller = _load_poller("gmail_poll.py", "gmail_poller_flow_test")
        fake_flow = FakeFlow()
        callback = "http://localhost:8766/?code=offline-code&state=state-123"

        credentials = poller._complete_phone_auth(
            fake_flow,
            read_callback=lambda _prompt: callback,
            write_output=lambda _line: None,
        )

        self.assertIs(credentials, fake_flow.credentials)
        self.assertEqual(
            fake_flow.callback,
            "https://localhost:8766/?code=offline-code&state=state-123",
        )
        self.assertEqual(fake_flow.redirect_uri, "http://localhost:8766/")

    def test_expired_credentials_without_refresh_token_fail_closed(self) -> None:
        class ExpiredCredentials:
            valid = False
            expired = True
            refresh_token = None

        for filename, token_name in (
            ("poll-calendar-google.py", "token.json"),
            ("gmail_poll.py", "gmail-token.json"),
        ):
            with self.subTest(filename=filename):
                poller = _load_poller(filename, f"google_missing_refresh_{filename}")
                with TemporaryDirectory() as temp_dir:
                    poller.TOKEN_FILE = Path(temp_dir) / token_name
                    poller.TOKEN_FILE.write_text("{}")
                    with patch.object(
                        poller.Credentials,
                        "from_authorized_user_file",
                        return_value=ExpiredCredentials(),
                    ), patch.object(poller, "log") as log:
                        self.assertIsNone(poller.get_service())

                messages = "\n".join(call.args[0] for call in log.call_args_list)
                self.assertIn("requires a refresh token", messages)

    def test_calendar_invalid_grant_retains_existing_token(self) -> None:
        poller = _load_poller(
            "poll-calendar-google.py",
            "google_calendar_poller_invalid_grant_test",
        )

        class ExpiredCredentials:
            valid = False
            expired = True
            refresh_token = "refresh-token"

            def refresh(self, _request):
                raise RuntimeError("invalid_grant: offline test rejection")

        with TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "token.json"
            token_path.write_text('{"refresh_token":"existing"}')
            poller.TOKEN_FILE = token_path
            with patch.object(
                poller.Credentials,
                "from_authorized_user_file",
                return_value=ExpiredCredentials(),
            ), patch.object(poller, "log") as log:
                self.assertIsNone(poller.get_service())

            self.assertEqual(token_path.read_text(), '{"refresh_token":"existing"}')
            messages = "\n".join(call.args[0] for call in log.call_args_list)
            self.assertIn("existing token.json was retained", messages)

    @unittest.skipUnless(
        REAL_OAUTH_LIBRARIES_AVAILABLE,
        "real google-auth-oauthlib/oauthlib libraries are not installed",
    )
    def test_real_oauthlib_accepts_validated_http_loopback_with_pkce(self) -> None:
        """Exercise the real parser and token exchange without network access."""

        poller = _load_poller_with_real_oauth(
            "poll-calendar-google.py",
            "google_calendar_poller_real_oauth_test",
        )
        token_uri = "https://oauth.example.invalid/token"
        client_config = {
            "installed": {
                "client_id": "offline-client-id",
                "project_id": "offline-project",
                "auth_uri": "https://oauth.example.invalid/auth",
                "token_uri": token_uri,
                "auth_provider_x509_cert_url": "https://oauth.example.invalid/cert",
                "client_secret": "offline-client-secret",
                "redirect_uris": ["http://localhost"],
            }
        }

        with TemporaryDirectory() as temp_dir:
            credentials_path = Path(temp_dir) / "credentials.json"
            credentials_path.write_text(json.dumps(client_config))
            flow = RealInstalledAppFlow.from_client_secrets_file(
                str(credentials_path),
                ["offline.scope"],
                autogenerate_code_verifier=True,
            )
            flow.redirect_uri = "http://localhost:8765/"
            authorization_url, state = flow.authorization_url(
                access_type="offline",
                prompt="consent",
            )
            authorization_query = parse_qs(urlsplit(authorization_url).query)
            verifier = flow.code_verifier

            self.assertTrue(verifier)
            self.assertEqual(authorization_query["state"], [state])
            self.assertEqual(authorization_query["access_type"], ["offline"])
            self.assertEqual(authorization_query["prompt"], ["consent"])
            self.assertEqual(authorization_query["code_challenge_method"], ["S256"])
            expected_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode("ascii")).digest()
            ).rstrip(b"=").decode("ascii")
            self.assertEqual(authorization_query["code_challenge"], [expected_challenge])

            callback = (
                f"http://localhost:8765/?code=offline-code&state={state}"
                "&scope=offline.scope"
            )
            authorization_response = poller._oauthlib_authorization_response(callback, state)
            self.assertTrue(authorization_response.startswith("https://localhost:8765/"))

            response = requests.Response()
            response.status_code = 200
            response.url = token_uri
            response.headers["content-type"] = "application/json"
            response._content = (
                b'{"access_token":"offline-access",'
                b'"token_type":"Bearer","refresh_token":"offline-refresh",'
                b'"expires_in":3600}'
            )
            request_calls = []

            def stub_token_request(method, url, **kwargs):
                request_calls.append((method, url, kwargs))
                return response

            flow.oauth2session.request = stub_token_request
            with self.assertRaises(Exception):
                flow.fetch_token(
                    authorization_response=(
                        authorization_response.replace(f"state={state}", "state=wrong-state")
                    )
                )
            self.assertEqual(request_calls, [])

            token = flow.fetch_token(authorization_response=authorization_response)
            self.assertEqual(token["access_token"], "offline-access")
            self.assertEqual(len(request_calls), 1)
            method, url, request_kwargs = request_calls[0]
            self.assertEqual(method, "POST")
            self.assertEqual(url, token_uri)
            token_request_data = request_kwargs["data"]
            if isinstance(token_request_data, str):
                token_request_data = parse_qs(token_request_data)
            verifier_value = token_request_data["code_verifier"]
            code_value = token_request_data["code"]
            if isinstance(verifier_value, list):
                verifier_value = verifier_value[0]
            if isinstance(code_value, list):
                code_value = code_value[0]
            self.assertEqual(verifier_value, verifier)
            self.assertEqual(code_value, "offline-code")

    def test_calendar_feed_readback_contains_freshness_marker(self) -> None:
        poller = _load_poller("poll-calendar-google.py", "google_calendar_poller_feed_test")

        with TemporaryDirectory() as temp_dir:
            poller.CALENDAR_MD = Path(temp_dir) / "GOOGLE_CALENDAR.md"
            with patch.object(poller, "log"):
                poller.write_calendar_md([])

            content = poller.CALENDAR_MD.read_text()
            self.assertIn("Last updated:", content)
            self.assertIn("No events in the next 14 days", content)


class FakeFlowThatFails(FakeFlow):
    def fetch_token(self, **_kwargs):
        raise RuntimeError("offline token exchange failure")


class FakeCredentialsWithoutRefresh(FakeCredentials):
    refresh_token = None


class FakeFlowWithoutRefresh(FakeFlow):
    def __init__(self) -> None:
        super().__init__()
        self.credentials = FakeCredentialsWithoutRefresh()


if __name__ == "__main__":
    unittest = __import__("unittest")
    unittest.main()