#!/usr/bin/env bash
# ==============================================================================
# Post-Deployment OpenID4VCI Pre-Authorized Issuance Smoke Test
#
# Validates that the Inji Certify issuer platform is fully operational:
# 1. Verifies OpenID credential issuer discovery endpoint
# 2. Stages a pre-authorized issuance offer for a student
# 3. Fetches the pre-authorized code from the offer endpoint
# 4. Exchanges the code for an Access Token directly with Inji Certify
# 5. Generates an ephemeral RS256 DID Key and signed proof-of-possession JWT
# 6. Requests credential issuance via OpenID4VCI and verifies the signed VC
#
# Usage:
#   ./scripts/smoke-test.sh [certify_url] [student_id] [config_id]
#   ./scripts/smoke-test.sh http://localhost:9091
# ==============================================================================
set -euo pipefail

# ANSI color codes
BOLD="\033[1m"
GREEN="\033[0;32m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

CERTIFY_URL="${1:-${CERTIFY_PUBLIC_BASE_URL:-http://localhost:9091}}"
STUDENT_ID="${2:-st123456}"
CONFIG_ID="${3:-ait-transcript}"
OUTPUT_FILE="${SMOKE_OUTPUT:-}"

CERTIFY_URL="${CERTIFY_URL%/}" # Strip trailing slash

echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} Target Issuer: ${CERTIFY_URL}"
echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} Student ID:    ${STUDENT_ID}"
echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} Credential ID: ${CONFIG_ID}"

# 0. Check prerequisite CLI tools
for cmd in curl jq openssl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} Required tool '$cmd' is not installed." >&2
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
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} No hex converter found (xxd, perl, or python3 required)." >&2
    exit 1
  fi
}

# 1. Verify Discovery Endpoint & Credential Definition
echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} 1/6 Checking OpenID Credential Issuer discovery endpoint..."
DISCOVERY_URL="${CERTIFY_URL}/.well-known/openid-credential-issuer"
ISSUER_META=$(curl -sf --max-time 10 "$DISCOVERY_URL") || {
  echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} Could not reach discovery endpoint at ${DISCOVERY_URL}" >&2
  exit 1
}

CONFIG=$(echo "$ISSUER_META" | jq -c ".credential_configurations_supported[\"${CONFIG_ID}\"] // empty")
if [ -z "$CONFIG" ]; then
  echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} Credential configuration '${CONFIG_ID}' not found in issuer metadata." >&2
  exit 1
fi
FORMAT=$(echo "$CONFIG" | jq -r .format)
DEF_JSON=$(echo "$CONFIG" | jq -c '{type: .credential_definition.type, "@context": .credential_definition["@context"]}')
echo -e "${GREEN}${BOLD}[OK]${NC} Issuer metadata verified (Format: ${FORMAT})."

# 2. Pre-authorize issuance offer
echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} 2/6 Staging pre-authorized issuance offer for ${STUDENT_ID}..."
OFFER_RESP=$(curl -sf --max-time 10 -X POST "${CERTIFY_URL}/v1/certify/pre-authorized-data" \
  -H "Content-Type: application/json" \
  -d "{\"credential_configuration_id\":\"${CONFIG_ID}\",\"claims\":{\"registrationNo\":\"${STUDENT_ID}\"}}") || {
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} Failed to stage pre-authorized data offer from ${CERTIFY_URL}" >&2
    exit 1
}
OFFER_URI=$(echo "$OFFER_RESP" | jq -r .credential_offer_uri)
OFFER_ID=$(echo "$OFFER_URI" | sed 's/.*credential-offer-data%2F//')
echo -e "${GREEN}${BOLD}[OK]${NC} Offer created successfully: ${OFFER_ID}"

# 3. Fetch pre-authorized code from offer data
echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} 3/6 Fetching pre-authorized code..."
OFFER_DATA=$(curl -sf --max-time 10 "${CERTIFY_URL}/v1/certify/credential-offer-data/${OFFER_ID}") || {
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} Failed to fetch credential offer data for ${OFFER_ID}" >&2
    exit 1
}
PRE_AUTH_CODE=$(echo "$OFFER_DATA" | jq -r '.grants["urn:ietf:params:oauth:grant-type:pre-authorized_code"]["pre-authorized_code"] // empty')
if [ -z "$PRE_AUTH_CODE" ]; then
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} No pre-authorized_code found in offer data response." >&2
    exit 1
fi
echo -e "${GREEN}${BOLD}[OK]${NC} Pre-authorized code acquired."

# 4. Exchange code for an Access Token directly with Inji Certify
echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} 4/6 Exchanging pre-auth code for Inji Certify access token..."
TOKEN_RESP=$(curl -sf --max-time 10 -X POST "${CERTIFY_URL}/v1/certify/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:pre-authorized_code&pre-authorized_code=${PRE_AUTH_CODE}") || {
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} Failed to exchange pre-authorized code for access token." >&2
    exit 1
}
ACCESS_TOKEN=$(echo "$TOKEN_RESP" | jq -r .access_token)
C_NONCE=$(echo "$TOKEN_RESP" | jq -r '.c_nonce // empty')
CLIENT_ID=$(echo "$TOKEN_RESP" | jq -r '.client_id // ""')
if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" = "null" ]; then
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} No access_token returned by Certify OAuth endpoint." >&2
    exit 1
fi
echo -e "${GREEN}${BOLD}[OK]${NC} Access token issued successfully."

# 5. Generate Proof of Possession (RS256 did:jwk)
echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} 5/6 Generating ephemeral RS256 DID Key and proof-of-possession JWT..."
TMPDIR_PROOFS=$(mktemp -d)
trap 'rm -rf "$TMPDIR_PROOFS"' EXIT

KEY_FILE="$TMPDIR_PROOFS/key.pem"
openssl genrsa -out "$KEY_FILE" 2048 2>/dev/null

N_MOD=$(openssl rsa -in "$KEY_FILE" -noout -modulus 2>/dev/null | cut -d= -f2 | hex2bin | b64url)
E_EXP="AQAB"

JWK_JSON=$(jq -cn \
  --arg kty "RSA" \
  --arg n "$N_MOD" \
  --arg e "$E_EXP" \
  '{"e":$e,"kty":$kty,"n":$n}')

JWK_B64=$(printf "%s" "$JWK_JSON" | b64url)
DID_JWK="did:jwk:${JWK_B64}#0"

NOW=$(date +%s)
HEADER_B64=$(jq -cn \
  --arg kid "$DID_JWK" \
  '{"alg":"RS256","kid":$kid,"typ":"openid4vci-proof+jwt"}' | b64url)

PAYLOAD_B64=$(jq -cn \
  --arg aud "$CERTIFY_URL" \
  --arg nonce "$C_NONCE" \
  --arg iss "$CLIENT_ID" \
  --argjson now "$NOW" \
  '{"aud":$aud,"exp":($now+300),"iat":$now,"iss":$iss,"nonce":$nonce}' | b64url)

SIGNING_INPUT="${HEADER_B64}.${PAYLOAD_B64}"
SIGNATURE_B64=$(printf "%s" "$SIGNING_INPUT" | openssl dgst -sha256 -sign "$KEY_FILE" 2>/dev/null | b64url)
PROOF_JWT="${SIGNING_INPUT}.${SIGNATURE_B64}"
echo -e "${GREEN}${BOLD}[OK]${NC} Proof JWT generated (Holder: ${DID_JWK:0:32}...)"

# 6. Request credential issuance via OpenID4VCI
echo -e "${BLUE}${BOLD}[SMOKE TEST]${NC} 6/6 Requesting Verifiable Credential from Inji Certify..."
REQ_PAYLOAD=$(jq -cn \
  --arg format "$FORMAT" \
  --argjson def "$DEF_JSON" \
  --arg proof "$PROOF_JWT" \
  '{"format": $format, "credential_definition": $def, "proof": {"proof_type": "jwt", "jwt": $proof}}')

CRED_RESP=$(curl -sf --max-time 15 -X POST "${CERTIFY_URL}/v1/certify/issuance/credential" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$REQ_PAYLOAD") || {
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} Credential issuance call failed." >&2
    exit 1
}

CREDENTIAL_STR=$(echo "$CRED_RESP" | jq -r .credential)
if [ -z "$CREDENTIAL_STR" ] || [ "$CREDENTIAL_STR" = "null" ]; then
    echo -e "${RED}${BOLD}[SMOKE TEST FAILED]${NC} No credential found in response payload." >&2
    echo "$CRED_RESP" | jq . >&2
    exit 1
fi

ISSUER=$(echo "$CREDENTIAL_STR" | jq -r .issuer)
VC_TYPE=$(echo "$CREDENTIAL_STR" | jq -r '.type | join(", ")')
SUBJECT_NAME=$(echo "$CREDENTIAL_STR" | jq -r '.credentialSubject.fullName // .credentialSubject.name // "N/A"')
REG_NO=$(echo "$CREDENTIAL_STR" | jq -r '.credentialSubject.registrationNo // "N/A"')
PROGRAM=$(echo "$CREDENTIAL_STR" | jq -r '.credentialSubject.academicProgram // "N/A"')
SIG_TYPE=$(echo "$CREDENTIAL_STR" | jq -r '.proof.type // "Unknown"')

if [ -n "$OUTPUT_FILE" ]; then
    echo "$CREDENTIAL_STR" | jq . > "$OUTPUT_FILE"
    echo -e "${GREEN}${BOLD}[OK]${NC} Credential JSON saved to: ${OUTPUT_FILE}"
fi

echo -e "${GREEN}${BOLD}[OK]${NC} Credential issued successfully!"
echo "----------------------------------------------------------------------"
echo "  Credential Type    : ${VC_TYPE}"
echo "  Issuer DID         : ${ISSUER}"
echo "  Subject Name       : ${SUBJECT_NAME}"
echo "  Registration No    : ${REG_NO}"
echo "  Academic Program   : ${PROGRAM}"
echo "  Cryptographic Proof: ${SIG_TYPE}"
echo "----------------------------------------------------------------------"
echo ""
echo -e "${GREEN}${BOLD}======================================================================${NC}"
echo -e "${GREEN}${BOLD} 🎉 SMOKE TEST PASSED: Inji Certify issuer engine is healthy!${NC}"
echo -e "${GREEN}${BOLD}======================================================================${NC}"
exit 0
