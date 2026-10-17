"""Phase 5: login challenges (2FA / device authorization / expired password)
must complete for people who sign in with their email address.

LoginView accepts a unique email in place of the username, but verify-otp,
resend-otp and expired-password-change look the account up by username. The
login page therefore continues every challenge with the canonical `username`
returned by the server (frontend/src/services/auth.js challengeAccount). These
tests run that exact sequence against the real views; OTP codes are read from
Django's test mail outbox (email delivery, never logged).
"""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from auth_app.models import AuthToken
from pos.models import UserProfile
from system.models import SecuritySettings

PASSWORD = "correct-horse-battery-staple"
NEW_PASSWORD = "Another-horse-42-battery"


def last_code():
    match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
    assert match, "no code in the delivered message"
    return match.group(1)


class LoginChallengeByEmailTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="sara.k", email="Sara@Example.test", password=PASSWORD,
        )
        self.security = SecuritySettings.load()
        self.security.two_factor_method = "email"
        self.security.save()

    def post(self, path, payload):
        cache.clear()  # per-username throttle is not under test here
        return self.client.post(path, payload, format="json")

    def test_two_factor_login_by_email_completes_with_the_canonical_username(self):
        self.security.two_factor_enabled = True
        self.security.save()
        challenge = self.post("/api/auth/login/", {"username": "sara@example.test", "password": PASSWORD, "device_id": "till-1"})
        self.assertEqual(challenge.status_code, 200, challenge.data)
        self.assertTrue(challenge.data["requires_2fa"])
        self.assertEqual(challenge.data["username"], "sara.k")
        self.assertNotIn("token", challenge.data)

        # What the page used to send: the typed email. The view refuses it.
        typed = self.post("/api/auth/verify-otp/", {"username": "sara@example.test", "code": last_code(), "device_id": "till-1"})
        self.assertEqual(typed.status_code, 400)

        resent = self.post("/api/auth/resend-otp/", {"username": challenge.data["username"], "device_id": "till-1"})
        self.assertEqual(resent.status_code, 200, resent.data)
        wrong = self.post("/api/auth/verify-otp/", {"username": "sara.k", "code": "000000" if last_code() != "000000" else "111111", "device_id": "till-1"})
        self.assertEqual(wrong.status_code, 400)

        done = self.post("/api/auth/verify-otp/", {"username": challenge.data["username"], "code": last_code(), "device_id": "till-1"})
        self.assertEqual(done.status_code, 200, done.data)
        self.assertTrue(AuthToken.objects.filter(user=self.user, key=done.data["token"], is_revoked=False).exists())
        # A used code cannot be replayed.
        replay = self.post("/api/auth/verify-otp/", {"username": "sara.k", "code": last_code(), "device_id": "till-1"})
        self.assertEqual(replay.status_code, 400)

    def test_device_authorization_then_two_factor(self):
        self.security.require_device_authorization = True
        self.security.two_factor_enabled = True
        self.security.save()
        first = self.post("/api/auth/login/", {"username": "SARA@example.test", "password": PASSWORD, "device_id": "till-9"})
        self.assertTrue(first.data["requires_device_authorization"])
        step = self.post("/api/auth/verify-otp/", {"username": first.data["username"], "code": last_code(), "device_id": "till-9"})
        self.assertEqual(step.status_code, 200, step.data)
        self.assertTrue(step.data["requires_2fa"])
        done = self.post("/api/auth/verify-otp/", {"username": step.data["username"], "code": last_code(), "device_id": "till-9"})
        self.assertEqual(done.status_code, 200, done.data)
        self.assertIn("token", done.data)

    def test_expired_password_change_by_email_uses_the_canonical_username(self):
        self.security.password_expiry_days = 30
        self.security.save()
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.password_changed_at = timezone.now() - timedelta(days=31)
        profile.save()
        expired = self.post("/api/auth/login/", {"username": "sara@example.test", "password": PASSWORD})
        self.assertEqual(expired.status_code, 403)
        self.assertTrue(expired.data["password_expired"])
        self.assertEqual(expired.data["username"], "sara.k")

        typed = self.post("/api/auth/expired-password-change/", {"username": "sara@example.test", "old_password": PASSWORD, "new_password": NEW_PASSWORD})
        self.assertEqual(typed.status_code, 401)
        changed = self.post("/api/auth/expired-password-change/", {"username": expired.data["username"], "old_password": PASSWORD, "new_password": NEW_PASSWORD})
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(self.post("/api/auth/login/", {"username": "sara@example.test", "password": NEW_PASSWORD}).status_code, 200)

    def test_password_reset_round_trip_and_enumeration_safety(self):
        unknown = self.post("/api/auth/password-reset/request/", {"email": "nobody@example.test"})
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        known = self.post("/api/auth/password-reset/request/", {"email": "sara@example.test"})
        self.assertEqual(known.data["message"], unknown.data["message"])
        old_token = AuthToken.objects.create(user=self.user)

        bad = self.post("/api/auth/password-reset/confirm/", {"email": "sara@example.test", "code": "x", "new_password": NEW_PASSWORD})
        self.assertEqual(bad.status_code, 400)
        weak = self.post("/api/auth/password-reset/confirm/", {"email": "sara@example.test", "code": last_code(), "new_password": "a"})
        self.assertEqual(weak.status_code, 400)
        self.assertIn("errors", weak.data)  # the page shows these policy messages
        done = self.post("/api/auth/password-reset/confirm/", {"email": "sara@example.test", "code": last_code(), "new_password": NEW_PASSWORD})
        self.assertEqual(done.status_code, 200, done.data)
        old_token.refresh_from_db()
        self.assertTrue(old_token.is_revoked)
        self.assertEqual(self.post("/api/auth/login/", {"username": "sara.k", "password": NEW_PASSWORD}).status_code, 200)
