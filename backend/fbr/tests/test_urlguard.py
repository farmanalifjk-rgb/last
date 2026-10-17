"""SSRF guard for the tenant-configured local IMS component URL (audit H4)."""
from django.test import SimpleTestCase, override_settings

from fbr.urlguard import validate_ims_local_base_url


class IMSLocalURLGuardTests(SimpleTestCase):
    def test_localhost_and_loopback_allowed(self):
        for url in (
            "http://localhost:8524",
            "http://127.0.0.1:8524",
            "https://127.0.0.1:8524",
            "http://[::1]:8524",
        ):
            with self.subTest(url=url):
                self.assertEqual(validate_ims_local_base_url(url), url)

    def test_private_lan_allowed(self):
        for url in ("http://192.168.1.10:8524", "http://10.0.0.5", "https://172.16.4.9:8524"):
            with self.subTest(url=url):
                self.assertEqual(validate_ims_local_base_url(url), url)

    def test_link_local_metadata_denied(self):
        for url in ("http://169.254.169.254/latest/meta-data", "http://fe80::1"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_ims_local_base_url(url)

    def test_public_hosts_and_dns_names_denied(self):
        for url in (
            "https://internal.example.com",
            "http://8.8.8.8",
            "http://metadata.google.internal",
            "http://100.64.0.1",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_ims_local_base_url(url)

    def test_non_http_schemes_denied(self):
        for url in ("ftp://192.168.1.10", "file:///etc/passwd", "gopher://127.0.0.1"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_ims_local_base_url(url)

    def test_error_messages_do_not_echo_the_url(self):
        with self.assertRaises(ValueError) as ctx:
            validate_ims_local_base_url("http://secret-host.corp.internal:9999")
        self.assertNotIn("secret-host", str(ctx.exception))

    @override_settings(FBR_IMS_EXTRA_ALLOWED_HOSTS=["pos-branch-01.corp"])
    def test_deployment_approved_host_allowed(self):
        url = "http://pos-branch-01.corp:8524"
        self.assertEqual(validate_ims_local_base_url(url), url)

    def test_client_rejects_disallowed_url_at_call_time(self):
        from fbr.ims_client import IMSFiscalClient, IMSTransportError

        class _Config:
            ims_use_cloud = False
            ims_local_base_url = "http://169.254.169.254"
            environment = "sandbox"
            verify_tls = True
            timeout_seconds = 5
            max_retries = 0
            security_token = ""

        with self.assertRaises(IMSTransportError):
            IMSFiscalClient(_Config()).health_check()
