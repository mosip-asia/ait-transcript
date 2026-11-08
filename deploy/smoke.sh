#!/usr/bin/env bash
# ==============================================================================
# OpenID4VCI Pre-Authorized Issuance Smoke Test
# ==============================================================================
# Tests the core Inji Certify issuer platform end-to-end without Keycloak or
# holder wallet dependencies, directly exercising:
#   1. Inji Certify Nginx Ingress & Engine (:9091)
#   2. Pre-Authorized Code issuance workflow
#   3. SPI DataProviderPlugin data resolution from Campus SIS Adapter
#   4. Dynamic JSON template rendering from GitOps config
#   5. Cryptographic proof-of-possession verification (RS256 did:jwk)
#   6. W3C VCDM 2.0 signature generation (Ed25519Signature2020)
#   7. Bitstring Status List revocation index allocation
#
# Usage:
#   ./deploy/smoke.sh [student_id] [certify_url] [config_id]
#
# Examples:
#   ./deploy/smoke.sh st123456
#   ./deploy/smoke.sh st123457 http://localhost:9091 ait-transcript
# ==============================================================================
set -euo pipefail

STUDENT_ID="${1:-st123456}"
CERTIFY_URL="${2:-${CERTIFY_PUBLIC_BASE_URL:-http://localhost:9091}}"
CONFIG_ID="${3:-ait-transcript}"
OUTPUT_FILE="${SMOKE_OUTPUT:-}"

# Strip trailing slash from URL
CERTIFY_URL="${CERTIFY_URL%/}"

echo "======================================================================"
echo " Starting OpenID4VCI Pre-Authorized Issuance Smoke Test"
echo " Target Issuer : ${CERTIFY_URL}"
echo " Student ID    : ${STUDENT_ID}"
echo " Credential ID : ${CONFIG_ID}"
echo "======================================================================"

# 0. Check prerequisite CLI tools
for cmd in curl jq openssl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[-] Error: Required tool '$cmd' is not installed." >&2
    exit 1
  fi
done

b64url() {
  base64 -w0 | tr '+/' '-_' | tr -d '='
}

hex2bin() {
  if command -v xxd >/dev/null 2>&1; then
    xxd -r -p
  elif command -v perl >/dev/null 2>&1; then
    perl -ne 'print pack("H*", $_)'
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import sys; sys.stdout.buffer.write(bytes.fromhex(sys.stdin.read().strip()))'
  else
    echo "[-] Error: No hex converter found (xxd, perl, or python3 required)." >&2
    exit 1
  fi
}

# 1. Pre-authorize issuance offer
echo -n "[1/6] Staging pre-authorized issuance offer for ${STUDENT_ID}... "
OFFER_RESP=$(curl -sf -X POST "${CERTIFY_URL}/v1/certify/pre-authorized-data" \
  -H "Content-Type: application/json" \
  -d "{\"credential_configuration_id\":\"${CONFIG_ID}\",\"claims\":{\"registrationNo\":\"${STUDENT_ID}\"}}") || {
    echo "FAILED"
    echo "[-] Error: Failed to stage pre-authorized data offer from ${CERTIFY_URL}" >&2
    exit 1
}
OFFER_URI=$(echo "$OFFER_RESP" | jq -r .credential_offer_uri)
OFFER_ID=$(echo "$OFFER_URI" | sed 's/.*credential-offer-data%2F//')
echo "OK (Offer: ${OFFER_ID})"

# 2. Fetch pre-authorized code from offer data
echo -n "[2/6] Fetching pre-authorized code... "
OFFER_DATA=$(curl -sf "${CERTIFY_URL}/v1/certify/credential-offer-data/${OFFER_ID}") || {
    echo "FAILED"
    echo "[-] Error: Failed to fetch credential offer data for ${OFFER_ID}" >&2
    exit 1
}
PRE_AUTH_CODE=$(echo "$OFFER_DATA" | jq -r '.grants["urn:ietf:params:oauth:grant-type:pre-authorized_code"]["pre-authorized_code"] // empty')
if [ -z "$PRE_AUTH_CODE" ]; then
    echo "FAILED"
    echo "[-] Error: No pre-authorized_code found in offer data response." >&2
    exit 1
fi
echo "OK"

# 3. Exchange code for an Access Token directly with Inji Certify
echo -n "[3/6] Exchanging pre-auth code for Inji Certify access token... "
TOKEN_RESP=$(curl -sf -X POST "${CERTIFY_URL}/v1/certify/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:pre-authorized_code&pre-authorized_code=${PRE_AUTH_CODE}") || {
    echo "FAILED"
    echo "[-] Error: Failed to exchange pre-authorized code for access token" >&2
    exit 1
}
ACCESS_TOKEN=$(echo "$TOKEN_RESP" | jq -r .access_token)
C_NONCE=$(echo "$TOKEN_RESP" | jq -r '.c_nonce // empty')
CLIENT_ID=$(echo "$TOKEN_RESP" | jq -r '.client_id // ""')
echo "OK (c_nonce: ${C_NONCE:-none})"

# 4. Fetch metadata for supported format and credential definition
echo -n "[4/6] Reading issuer metadata and credential definition... "
ISSUER_META=$(curl -sf "${CERTIFY_URL}/.well-known/openid-credential-issuer") || {
    echo "FAILED"
    echo "[-] Error: Failed to fetch openid-credential-issuer metadata" >&2
    exit 1
}
CONFIG=$(echo "$ISSUER_META" | jq -c ".credential_configurations_supported[\"${CONFIG_ID}\"] // empty")
if [ -z "$CONFIG" ]; then
    echo "FAILED"
    echo "[-] Error: Credential configuration '${CONFIG_ID}' not found in issuer metadata." >&2
    exit 1
fi
FORMAT=$(echo "$CONFIG" | jq -r .format)
DEF_JSON=$(echo "$CONFIG" | jq -c '{type: .credential_definition.type, "@context": .credential_definition["@context"]}')
echo "OK (Format: ${FORMAT})"

# 5. Generate ephemeral RSA key and construct RS256 Proof-of-Possession JWT
echo -n "[5/6] Generating cryptographic Proof-of-Possession JWT (did:jwk)... "
TMP_KEY=$(mktemp)
trap 'rm -f "$TMP_KEY"' EXIT
openssl genrsa -out "$TMP_KEY" 2048 >/dev/null 2>&1
MOD_HEX=$(openssl rsa -in "$TMP_KEY" -modulus -noout | cut -d= -f2)
MOD_B64=$(printf "%s" "$MOD_HEX" | hex2bin | b64url)
EXP_B64="AQAB"

JWK=$(jq -cn --arg n "$MOD_B64" --arg e "$EXP_B64" '{"e":$e,"kty":"RSA","n":$n}')
KID="did:jwk:$(printf "%s" "$JWK" | b64url)#0"

HEADER=$(jq -cn --arg kid "$KID" '{"alg":"RS256","kid":$kid,"typ":"openid4vci-proof+jwt"}' | b64url)
NOW=$(date +%s)
PAYLOAD=$(jq -cn --arg iss "$CLIENT_ID" --arg aud "$CERTIFY_URL" --arg nonce "$C_NONCE" --argjson now "$NOW" \
  '{"aud":$aud,"exp":($now+300),"iat":$now,"iss":$iss,"nonce":$nonce}' | b64url)
SIGNING_INPUT="${HEADER}.${PAYLOAD}"
SIG=$(printf "%s" "$SIGNING_INPUT" | openssl dgst -sha256 -sign "$TMP_KEY" | b64url)
PROOF_JWT="${SIGNING_INPUT}.${SIG}"
echo "OK"

# 6. Request signed Verifiable Credential
echo -n "[6/6] Requesting signed Verifiable Credential from Certify engine... "
ISSUANCE_RESP=$(curl -sf -X POST "${CERTIFY_URL}/v1/certify/issuance/credential" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"format\": \"${FORMAT}\",
    \"credential_definition\": ${DEF_JSON},
    \"proof\": {
      \"proof_type\": \"jwt\",
      \"jwt\": \"${PROOF_JWT}\"
    }
  }") || {
    echo "FAILED"
    echo "[-] Error: Credential issuance request failed." >&2
    exit 1
}
echo "OK"

# Verification & Inspection
FULL_NAME=$(echo "$ISSUANCE_RESP" | jq -r '.credential.credentialSubject.fullName // empty')
REG_NO=$(echo "$ISSUANCE_RESP" | jq -r '.credential.credentialSubject.registrationNo // empty')
DEGREE=$(echo "$ISSUANCE_RESP" | jq -r '.credential.credentialSubject.degreeAwarded // empty')
ISSUER_DID=$(echo "$ISSUANCE_RESP" | jq -r '.credential.issuer // empty')
PROOF_TYPE=$(echo "$ISSUANCE_RESP" | jq -r '.credential.proof.type // empty')
STATUS_PURPOSE=$(echo "$ISSUANCE_RESP" | jq -r '.credential.credentialStatus.statusPurpose // empty')
STATUS_INDEX=$(echo "$ISSUANCE_RESP" | jq -r '.credential.credentialStatus.statusListIndex // empty')

if [ -z "$FULL_NAME" ] || [ -z "$ISSUER_DID" ]; then
    echo "[-] Error: Issued credential response missing expected fields." >&2
    echo "$ISSUANCE_RESP" | jq .
    exit 1
fi

echo "======================================================================"
echo " [+] SMOKE TEST PASSED: Verifiable Credential Successfully Issued!"
echo "----------------------------------------------------------------------"
echo " Subject Name     : ${FULL_NAME}"
echo " Registration No  : ${REG_NO}"
echo " Degree Awarded   : ${DEGREE}"
echo " Issuer DID       : ${ISSUER_DID}"
echo " Proof Type       : ${PROOF_TYPE}"
echo " Status Purpose   : ${STATUS_PURPOSE} (Index: ${STATUS_INDEX})"
echo "======================================================================"

if [ -n "$OUTPUT_FILE" ]; then
    echo "$ISSUANCE_RESP" | jq . > "$OUTPUT_FILE"
    echo "[+] Full credential JSON written to: ${OUTPUT_FILE}"
fi
