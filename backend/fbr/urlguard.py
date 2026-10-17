"""URL allowlist for the tenant-configured local IMS fiscal component.

The fiscal component lives on the taxpayer's own POS PC, so a legitimate
``ims_local_base_url`` points at the loopback interface or the private LAN.
Anything else is a server-side request forgery vector (cloud metadata, internal
admin panels), so this module rejects it before any request is made:

* scheme must be ``http`` or ``https``;
* host must be ``localhost``, a loopback IP, or an RFC1918 private IP;
* link-local addresses (``169.254.0.0/16`` — cloud metadata) are always denied;
* deployments may allow additional host names (e.g. a docker-compose service
  name or a LAN host name) via the ``FBR_IMS_EXTRA_ALLOWED_HOSTS`` setting
  (comma-separated, exact host match, case-insensitive).

Cloud mode (``ims_use_cloud``) never uses this validator — its endpoints are
platform constants.
"""
import ipaddress
from urllib.parse import urlparse

from django.conf import settings

ALLOWED_SCHEMES = ("http", "https")


def _extra_allowed_hosts():
    raw = getattr(settings, "FBR_IMS_EXTRA_ALLOWED_HOSTS", "") or ""
    if isinstance(raw, (list, tuple)):
        return {str(h).strip().lower().rstrip(".") for h in raw if str(h).strip()}
    return {h.strip().lower().rstrip(".") for h in str(raw).split(",") if h.strip()}


def validate_di_endpoint_url(url):
    """Validate a tenant-supplied DI endpoint override (SSRF guard).

    The DI ``endpoint_url`` lets a deployment override the published FBR
    gateway for an environment. It must be a public HTTPS/HTTP endpoint —
    pointing it at a loopback, private, link-local or reserved address would
    let a tenant turn the platform's outbound fiscal client into a server-side
    request forgery proxy (cloud metadata, internal admin panels, LAN
    services). The rejected value is never echoed back, so internal hostnames
    cannot be smuggled out through validation errors.
    """
    url = (url or "").strip()
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except ValueError:
        raise ValueError("The FBR endpoint URL is malformed.") from None
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("The FBR endpoint URL must use http or https.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("The FBR endpoint URL must include a host.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Not a literal IP: it must be a qualified hostname. Bare single-label
        # names are the classic internal-service/SSRF target (e.g. "intranet",
        # "metadata", "database").
        if host == "localhost" or "." not in host:
            raise ValueError(
                "The FBR endpoint host must be a public hostname or a public IP address."
            )
        return url
    if not ip.is_global:
        raise ValueError(
            "The FBR endpoint must be a public host; private, loopback, link-local "
            "and reserved addresses are not allowed."
        )
    return url


def validate_ims_local_base_url(url):
    """Return *url* when allowed for local-component posting.

    Raises ``ValueError`` with a tenant-safe message otherwise. The message
    never echoes the rejected URL back, so internal hostnames cannot be
    smuggled out through validation errors.
    """
    try:
        parsed = urlparse(url or "")
    except ValueError:
        raise ValueError("The IMS component URL is malformed.") from None
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("The IMS component URL must use http or https.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("The IMS component URL must include a host.")
    if host in _extra_allowed_hosts():
        return url
    if host == "localhost":
        return url
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError(
            "The IMS component host must be localhost, a loopback/private IP address, "
            "or a deployment-approved host. Use cloud mode (ims_use_cloud) for remote fiscalization."
        ) from None
    if ip.is_link_local:
        raise ValueError("Link-local addresses are not allowed for the IMS component URL.")
    if ip.is_loopback or ip.is_private:
        return url
    raise ValueError(
        "The IMS component host must be loopback or a private LAN address; "
        "use cloud mode (ims_use_cloud) for remote fiscalization."
    )


__all__ = ["validate_di_endpoint_url", "validate_ims_local_base_url"]
