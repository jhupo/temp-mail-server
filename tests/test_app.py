import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import suppress

from fastapi.testclient import TestClient


APP_MODULES = [
    "app.config",
    "app.database",
    "app.models",
    "app.security",
    "app.utils",
    "app.crud",
    "app.rate_limit",
    "app.main",
]


def reload_app_stack():
    for name in APP_MODULES:
        sys.modules.pop(name, None)

    config = importlib.import_module("app.config")
    database = importlib.import_module("app.database")
    importlib.import_module("app.models")
    utils = importlib.import_module("app.utils")
    crud = importlib.import_module("app.crud")
    rate_limit = importlib.import_module("app.rate_limit")
    main = importlib.import_module("app.main")
    database.init_db()
    return config, database, utils, crud, rate_limit, main


class TempMailTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.original_env = os.environ.copy()
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path.as_posix()}"
        os.environ["ALLOWED_ROOT_DOMAINS"] = "alpha.test,beta.test"
        os.environ["ALLOWED_ROOT_DOMAIN"] = "alpha.test"
        os.environ["MAILBOX_DEFAULT_TTL_MINUTES"] = "60"
        os.environ["ALLOW_AUTO_CREATE_ON_SMTP"] = "true"
        os.environ["REDIS_URL"] = ""
        os.environ["RATE_LIMIT_NEW_PER_MINUTE"] = "50"
        os.environ["CLEANUP_INTERVAL_SECONDS"] = "3600"
        os.environ.pop("API_MASTER_KEY", None)

        self.config, self.database, self.utils, self.crud, self.rate_limit, self.main = reload_app_stack()

    def tearDown(self):
        self.database.engine.dispose()
        for name in APP_MODULES:
            sys.modules.pop(name, None)
        os.environ.clear()
        os.environ.update(self.original_env)
        with suppress(PermissionError):
            self.temp_dir.cleanup()

    def make_client(self):
        return TestClient(self.main.app)

    def session(self):
        return self.main.SessionLocal()


class ApiBehaviorTests(TempMailTestCase):
    def test_admin_endpoints_disabled_without_master_key(self):
        with self.make_client() as client:
            response = client.get("/admin/mails")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "admin API disabled")

    def test_inbox_create_uses_first_allowed_domain(self):
        with self.make_client() as client:
            response = client.post("/inbox/create", headers={"x-forwarded-for": "10.0.0.1"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["address"].endswith("@alpha.test"))

    def test_admin_can_create_mailbox_on_secondary_allowed_domain(self):
        os.environ["API_MASTER_KEY"] = "secret-key"
        self.config, self.database, self.utils, self.crud, self.rate_limit, self.main = reload_app_stack()

        with self.make_client() as client:
            response = client.post(
                "/admin/new_address",
                headers={"x-admin-auth": "secret-key", "x-forwarded-for": "10.0.0.2"},
                json={"name": "demo", "domain": "beta.test"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["address"], "demo@beta.test")

    def test_rate_limit_blocks_repeated_mailbox_creation(self):
        os.environ["RATE_LIMIT_NEW_PER_MINUTE"] = "1"
        self.config, self.database, self.utils, self.crud, self.rate_limit, self.main = reload_app_stack()

        with self.make_client() as client:
            first = client.post("/inbox/create", headers={"x-forwarded-for": "10.0.0.3"})
            second = client.post("/inbox/create", headers={"x-forwarded-for": "10.0.0.3"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["detail"], "rate limit exceeded")
        self.assertIn("Retry-After", second.headers)


class MailboxClaimTests(TempMailTestCase):
    def test_auto_created_mailbox_can_be_claimed_by_admin(self):
        os.environ["API_MASTER_KEY"] = "secret-key"
        self.config, self.database, self.utils, self.crud, self.rate_limit, self.main = reload_app_stack()

        with self.session() as db:
            self.crud.save_incoming_message(
                db,
                recipient="claimme@beta.test",
                from_addr="sender@example.net",
                subject="hello",
                text_body="body",
                html_body=None,
                raw_headers="Subject: hello",
            )

        with self.make_client() as client:
            response = client.post(
                "/admin/new_address",
                headers={"x-admin-auth": "secret-key", "x-forwarded-for": "10.0.0.4"},
                json={"name": "claimme", "domain": "beta.test"},
            )

        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]
        self.assertTrue(token)

        with self.session() as db:
            mailbox = self.crud.get_mailbox_by_token(db, token)

        self.assertIsNotNone(mailbox)
        self.assertEqual(mailbox.address, "claimme@beta.test")

    def test_get_mailbox_by_token_returns_exact_mailbox(self):
        with self.session() as db:
            mailbox_one, token_one = self.crud.create_mailbox(
                db,
                domain="alpha.test",
                local_part="one",
                ttl_minutes=60,
            )
            mailbox_two, _token_two = self.crud.create_mailbox(
                db,
                domain="beta.test",
                local_part="two",
                ttl_minutes=60,
            )
            found = self.crud.get_mailbox_by_token(db, token_one)

        self.assertIsNotNone(found)
        self.assertEqual(found.id, mailbox_one.id)
        self.assertNotEqual(found.id, mailbox_two.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
