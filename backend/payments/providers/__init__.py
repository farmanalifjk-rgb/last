from .stripe import StripeProvider


REGISTERED_ADAPTERS = {
    StripeProvider.code: StripeProvider,
}


def get_provider(code):
    adapter = REGISTERED_ADAPTERS.get((code or "").strip().lower())
    if adapter is None:
        raise ValueError("The requested payment provider is not registered.")
    return adapter()


def registered_provider_codes():
    return tuple(REGISTERED_ADAPTERS)


def registered_providers():
    return tuple(adapter() for adapter in REGISTERED_ADAPTERS.values())


__all__ = ["StripeProvider", "get_provider", "registered_provider_codes", "registered_providers"]
