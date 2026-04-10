import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import suppress
import base64
from unittest.mock import patch

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

    def test_cloud_mail_register_login_and_settings(self):
        with self.make_client() as client:
            register = client.post(
                "/register",
                json={"email": "demo@alpha.test", "password": "secret12"},
            )
            self.assertEqual(register.status_code, 200)
            token = register.json()["data"]["token"]

            login = client.post(
                "/login",
                json={"email": "demo@alpha.test", "password": "secret12"},
            )
            self.assertEqual(login.status_code, 200)
            self.assertTrue(login.json()["data"]["token"])

            user_info = client.get("/my/loginUserInfo", headers={"Authorization": token})
            self.assertEqual(user_info.status_code, 200)
            self.assertEqual(user_info.json()["data"]["email"], "demo@alpha.test")

            website_config = client.get("/setting/websiteConfig")
            self.assertEqual(website_config.status_code, 200)
            self.assertIn("@alpha.test", website_config.json()["data"]["domainList"])

            setting_set = client.put(
                "/setting/set",
                headers={"Authorization": token},
                json={"title": "New Title", "autoRefresh": 15},
            )
            self.assertEqual(setting_set.status_code, 200)
            self.assertEqual(setting_set.json()["data"]["title"], "New Title")

            setting_query = client.get("/setting/query")
            self.assertEqual(setting_query.status_code, 200)
            self.assertEqual(setting_query.json()["data"]["autoRefresh"], 15)

    def test_cloud_mail_account_and_email_compat_routes(self):
        with self.make_client() as client:
            register = client.post(
                "/register",
                json={"email": "owner@alpha.test", "password": "secret12"},
            )
            token = register.json()["data"]["token"]

            added = client.post(
                "/account/add",
                headers={"Authorization": token},
                json={"email": "extra@beta.test"},
            )
            self.assertEqual(added.status_code, 200)

            account_list = client.get("/account/list", headers={"Authorization": token})
            self.assertEqual(account_list.status_code, 200)
            accounts = account_list.json()["data"]
            self.assertEqual(len(accounts), 2)

            with self.session() as db:
                self.crud.save_incoming_message(
                    db,
                    recipient="owner@alpha.test",
                    from_addr="sender@example.net",
                    subject="compat",
                    text_body="hello",
                    html_body="<p>hello</p>",
                    raw_headers="Subject: compat",
                )

            email_list = client.get(
                "/email/list",
                headers={"Authorization": token},
                params={"accountId": accounts[0]["accountId"], "allReceive": 1, "emailId": 0, "size": 50},
            )
            self.assertEqual(email_list.status_code, 200)
            self.assertEqual(email_list.json()["data"]["total"], 1)

    def test_settings_flags_change_runtime_behavior(self):
        with self.make_client() as client:
            register = client.post(
                "/register",
                json={"email": "owner@alpha.test", "password": "secret12"},
            )
            token = register.json()["data"]["token"]

            disable_register = client.put(
                "/setting/set",
                headers={"Authorization": token},
                json={"register": 1, "addEmail": 1, "send": 1, "minEmailPrefix": 5},
            )
            self.assertEqual(disable_register.status_code, 200)

            register_blocked = client.post(
                "/register",
                json={"email": "next@alpha.test", "password": "secret12"},
            )
            self.assertEqual(register_blocked.status_code, 200)
            self.assertEqual(register_blocked.json()["code"], 403)

            add_account_blocked = client.post(
                "/account/add",
                headers={"Authorization": token},
                json={"email": "ab@beta.test"},
            )
            self.assertEqual(add_account_blocked.status_code, 200)
            self.assertEqual(add_account_blocked.json()["code"], 403)

            send_blocked = client.post(
                "/email/send",
                headers={"Authorization": token},
                json={
                    "accountId": 1,
                    "sendEmail": "owner@alpha.test",
                    "name": "owner",
                    "receiveEmail": ["to@example.net"],
                    "subject": "test",
                    "content": "<p>hello</p>",
                    "text": "hello",
                },
            )
            self.assertEqual(send_blocked.status_code, 200)
            self.assertEqual(send_blocked.json()["code"], 403)

    def test_allowed_domains_can_be_changed_from_settings(self):
        with self.make_client() as client:
            register = client.post(
                "/register",
                json={"email": "owner@alpha.test", "password": "secret12"},
            )
            token = register.json()["data"]["token"]

            setting = client.put(
                "/setting/set",
                headers={"Authorization": token},
                json={"allowedDomains": ["gamma.test"]},
            )
            self.assertEqual(setting.status_code, 200)
            self.assertEqual(setting.json()["data"]["allowedDomains"], ["gamma.test"])

            blocked = client.post(
                "/register",
                json={"email": "new@alpha.test", "password": "secret12"},
            )
            self.assertEqual(blocked.json()["code"], 400)

            allowed = client.post(
                "/register",
                json={"email": "new@gamma.test", "password": "secret12"},
            )
            self.assertEqual(allowed.json()["code"], 200)

    def test_background_and_attachment_object_storage(self):
        png_payload = "data:image/png;base64," + base64.b64encode(b"fakepng").decode()
        txt_payload = base64.b64encode(b"hello attachment").decode()

        with self.make_client() as client:
            register = client.post(
                "/register",
                json={"email": "owner@alpha.test", "password": "secret12"},
            )
            token = register.json()["data"]["token"]

            client.put(
                "/setting/set",
                headers={"Authorization": token},
                json={"send": 0},
            )

            background = client.put(
                "/setting/setBackground",
                headers={"Authorization": token},
                json={"background": png_payload},
            )
            self.assertEqual(background.status_code, 200)
            background_key = background.json()["data"]
            self.assertTrue(background_key.startswith("/oss/"))

            background_fetch = client.get(background_key)
            self.assertEqual(background_fetch.status_code, 200)

            user_info = client.get("/my/loginUserInfo", headers={"Authorization": token})
            account_id = user_info.json()["data"]["account"]["accountId"]

            send = client.post(
                "/email/send",
                headers={"Authorization": token},
                json={
                    "accountId": account_id,
                    "sendEmail": "owner@alpha.test",
                    "name": "owner",
                    "receiveEmail": ["to@example.net"],
                    "subject": "with attachment",
                    "content": "<p>hello</p>",
                    "text": "hello",
                    "attachments": [
                        {
                            "filename": "note.txt",
                            "content": txt_payload,
                            "size": 16,
                            "contentType": "text/plain",
                        }
                    ],
                },
            )
            self.assertEqual(send.status_code, 200)
            item = send.json()["data"][0]
            self.assertEqual(len(item["attList"]), 1)
            attachment_key = item["attList"][0]["key"]
            attachment_fetch = client.get(attachment_key)
            self.assertEqual(attachment_fetch.status_code, 200)

    def test_smtp_send_mode_uses_mailer(self):
        with self.make_client() as client:
            register = client.post(
                "/register",
                json={"email": "owner@alpha.test", "password": "secret12"},
            )
            token = register.json()["data"]["token"]

            client.put(
                "/setting/set",
                headers={"Authorization": token},
                json={
                    "send": 0,
                    "sendMode": "smtp",
                    "smtpHost": "smtp.example.test",
                    "smtpPort": 587,
                    "smtpUseTls": True,
                    "smtpUseSsl": False,
                    "smtpFromEmail": "owner@alpha.test",
                },
            )

            user_info = client.get("/my/loginUserInfo", headers={"Authorization": token})
            account_id = user_info.json()["data"]["account"]["accountId"]

            with patch("app.main.send_via_smtp") as mocked_send:
                response = client.post(
                    "/email/send",
                    headers={"Authorization": token},
                    json={
                        "accountId": account_id,
                        "sendEmail": "owner@alpha.test",
                        "name": "owner",
                        "receiveEmail": ["to@example.net"],
                        "subject": "smtp send",
                        "content": "<p>hello</p>",
                        "text": "hello",
                    },
                )

            self.assertEqual(response.status_code, 200)
            mocked_send.assert_called_once()

    def test_certificate_apply_endpoint_uses_certbot_runner(self):
        with self.make_client() as client:
            register = client.post(
                "/register",
                json={"email": "owner@alpha.test", "password": "secret12"},
            )
            token = register.json()["data"]["token"]

            client.put(
                "/setting/set",
                headers={"Authorization": token},
                json={"certDomain": "mail.alpha.test", "certEmail": "admin@alpha.test"},
            )

            with patch("app.main.run_certbot_script") as mocked_certbot:
                mocked_certbot.return_value = {"ok": True, "message": "certificate issued"}
                response = client.post("/cert/apply", headers={"Authorization": token})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"]["status"], "ok")
            mocked_certbot.assert_called_once()

    def test_default_superadmin_and_admin_endpoints(self):
        with self.make_client() as client:
            login = client.post("/login", json={"email": "superadmin", "password": "sueradmin"})
            self.assertEqual(login.status_code, 200)
            token = login.json()["data"]["token"]

            role_list = client.get("/role/list", headers={"Authorization": token})
            self.assertEqual(role_list.status_code, 200)
            self.assertGreaterEqual(len(role_list.json()["data"]), 1)

            user_list = client.get("/user/list", headers={"Authorization": token})
            self.assertEqual(user_list.status_code, 200)
            self.assertGreaterEqual(user_list.json()["data"]["total"], 1)

            add_reg = client.post(
                "/regKey/add",
                headers={"Authorization": token},
                json={"code": "INVITE01", "count": 2, "roleId": 1, "expireTime": None},
            )
            self.assertEqual(add_reg.status_code, 200)

            reg_list = client.get("/regKey/list", headers={"Authorization": token})
            self.assertEqual(reg_list.status_code, 200)
            self.assertTrue(any(item["code"] == "INVITE01" for item in reg_list.json()["data"]))


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


class ForwardingTests(TempMailTestCase):
    def test_forward_all_recipients_uses_smtp_when_enabled(self):
        self.config, self.database, self.utils, self.crud, self.rate_limit, self.main = reload_app_stack()
        smtp_server = importlib.import_module("app.smtp_server")

        with self.session() as db:
            self.crud.update_app_settings(
                db,
                {
                    "forwardStatus": 0,
                    "forwardEmail": "dest1@example.net,dest2@example.net",
                    "ruleType": 0,
                    "smtpHost": "smtp.example.test",
                    "smtpPort": 587,
                    "smtpUseTls": True,
                    "smtpUseSsl": False,
                    "smtpFromEmail": "relay@example.net",
                },
            )
            app_settings = self.crud.get_app_settings(db)

        with patch("app.smtp_server.send_via_smtp") as mocked_send:
            smtp_server._forward_message_if_needed(
                app_settings,
                recipient_address="owner@alpha.test",
                from_addr="sender@example.org",
                subject="hello",
                text_body="body",
                html_body="<p>body</p>",
            )

        mocked_send.assert_called_once()
        self.assertEqual(mocked_send.call_args.kwargs["to_emails"], ["dest1@example.net", "dest2@example.net"])

    def test_forward_rules_limit_recipient_match(self):
        smtp_server = importlib.import_module("app.smtp_server")
        app_settings = {
            "forwardStatus": 0,
            "forwardEmail": "dest@example.net",
            "ruleType": 1,
            "ruleEmail": "match@alpha.test",
            "smtpHost": "smtp.example.test",
            "smtpPort": 587,
            "smtpUseTls": True,
            "smtpUseSsl": False,
            "smtpFromEmail": "relay@example.net",
        }

        with patch("app.smtp_server.send_via_smtp") as mocked_send:
            smtp_server._forward_message_if_needed(
                app_settings,
                recipient_address="miss@alpha.test",
                from_addr="sender@example.org",
                subject="hello",
                text_body="body",
                html_body=None,
            )
        mocked_send.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
