import importlib.util
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("health_check.py")
spec = importlib.util.spec_from_file_location("health_check", MODULE_PATH)
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class HealthCheckTests(TestCase):
    def test_user_systemctl_supplies_cron_safe_user_bus(self):
        with patch.object(health, "_run", return_value=(0, "enabled", "")) as run:
            self.assertEqual(
                health._run_user_systemctl("is-enabled", "expense-intake-watcher.timer"),
                (0, "enabled", ""),
            )
        self.assertEqual(
            run.call_args.args[0],
            ["systemctl", "--user", "is-enabled", "expense-intake-watcher.timer"],
        )
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["XDG_RUNTIME_DIR"], str(health.USER_RUNTIME_DIR))
        self.assertEqual(env["DBUS_SESSION_BUS_ADDRESS"], health.USER_BUS_ADDRESS)

    def test_expense_health_fails_closed_when_timer_is_disabled(self):
        state = Path(self.id().replace('.', '_') + '.json')
        try:
            state.write_text('{"last_run":"2026-07-24T09:53:33Z","last_summary":{}}')
            with patch.object(health, "EXPENSE_WATCHER_STATE", state), \
                 patch.object(health, "_mtime_age_minutes", return_value=0), \
                 patch.object(health, "_run_user_systemctl", side_effect=[(1, "disabled", ""), (0, "active", ""), (0, "enabled", ""), (0, "active", "")]):
                issues = health.check_expense_watcher_health()
            self.assertIn("Expense watcher: timer is not enabled", issues)
        finally:
            state.unlink(missing_ok=True)

    def test_expense_health_surfaces_all_mirror_blockers(self):
        state = Path(self.id().replace('.', '_') + '.json')
        try:
            state.write_text('{"last_run":"2026-08-10T10:00:00Z","last_summary":{"mirror_blocked":2}}')
            with patch.object(health, "EXPENSE_WATCHER_STATE", state), \
                 patch.object(health, "_mtime_age_minutes", return_value=0), \
                 patch.object(health, "_run_user_systemctl", side_effect=[(0, "enabled", ""), (0, "active", ""), (0, "enabled", ""), (0, "active", "")]):
                issues = health.check_expense_watcher_health()
            self.assertIn("Expense watcher: 2 blocked item(s) in latest run — review expense intake blockers", issues)
        finally:
            state.unlink(missing_ok=True)

    def test_diagnostic_info_does_not_create_a_user_facing_health_alert(self):
        self.assertEqual(
            health.build_health_report([], ["workspace repo: local working tree dirty"]),
            "",
        )

    def test_expense_health_uses_user_systemctl_not_ambient_cron_environment(self):
        state = Path(self.id().replace('.', '_') + '.json')
        try:
            state.write_text('{"last_run":"2026-07-24T09:53:33Z","last_summary":{}}')
            with patch.object(health, "EXPENSE_WATCHER_STATE", state), \
                 patch.object(health, "_mtime_age_minutes", return_value=0), \
                 patch.object(health, "_run_user_systemctl", side_effect=[(0, "enabled", ""), (0, "active", ""), (0, "enabled", ""), (0, "active", "")]) as run:
                self.assertEqual(health.check_expense_watcher_health(), [])
            self.assertEqual(run.call_count, 4)
        finally:
            state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
