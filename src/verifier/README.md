# AIT Verifier UI (Inji Verify Customization)

This directory defines the **custom branded Inji Verify UI** for the AIT Verifiable Credential platform.

## Architecture

Instead of writing a verifier from scratch, it extends the official upstream `injistack/inji-verify-ui:0.17.0` Docker image:

1. **Logo & Visual Identity:**
   - [`assets/inji_verify.svg`](assets/inji_verify.svg): Replaces upstream MOSIP logo with AIT Verify academic branding.
2. **Brand Theming:**
   - [`theme.css`](theme.css): Injected into `index.html` to override Inji's native `--iv-*` CSS variables with AIT's teal palette (`#0f766e`, `#0d9488`, slate neutrals).
3. **Configuration & Accepted Credentials:**
   - [`deploy/base/verify-config.json`](../../deploy/base/verify-config.json): Declaratively defines the accepted verifiable credentials (`AitTranscriptCredential`, `DeveloperPassportCredential`) and their rendered attributes (`VCRenderOrders`).
4. **Backend Engine:**
   - Runs alongside `injistack/inji-verify-service:0.17.0` (port `9095:8080`) backed by PostgreSQL. Nginx inside the container transparently proxies `/v1/verify` to the backend service.

## Usage

Start the verifier stack:
```bash
docker compose -f compose.yaml -f compose.verify.yaml up -d --build
```
Access the custom verifier at [http://localhost:4007](http://localhost:4007).

## Testing

Run contract verification:
```bash
python3 src/verifier/test_verifier.py
```
