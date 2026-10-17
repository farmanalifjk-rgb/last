# Production credential encryption

FBR Digital Invoicing credentials and fiscal-device API keys are encrypted at rest with Fernet authenticated encryption.

## Required production setting

Set `FBR_CREDENTIAL_ENCRYPTION_KEY` to a dedicated Fernet key. Generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep the key outside source control and inject it through the production secret-management mechanism. Do not reuse the development/test fallback or commit the generated value to `.env`, Git, or application code.

## Existing deployments

Migrations `fbr.0005_encrypt_credentials` and `fiscal.0009_encrypt_device_credentials` rewrite existing non-empty credentials into encrypted form. The application still decrypts them transparently when sending requests to FBR or fiscal devices.

## Key rotation

The current implementation intentionally fails closed if the configured encryption key cannot decrypt an existing credential. Before rotating the key, plan a controlled credential re-encryption migration that decrypts with the old key and re-encrypts with the new key. Do not simply replace the key in production.
