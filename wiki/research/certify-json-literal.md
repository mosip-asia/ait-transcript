# Does Certify 0.14 and Verify 0.17 JSON-LD processing accept `@json`?

Research note, written 2026-10-20 against upstream source. **Answer from source: yes on both ends; observed on the running stack on 2026-10-21 (section 4).** It settles the open point in [`signing-coverage.md`](signing-coverage.md) ("Whether Titanium in the Certify 0.14 image accepts `@json` is unchecked") for option 1a (claim terms at the top level of the context, `courses` typed `"@type": "@json"`).

## Short answer

Both the signing path in Inji Certify 0.14 and the verifying path in Inji Verify 0.17 run the credential through Titanium JSON-LD, a JSON-LD 1.1 processor whose default processing mode is 1.1 and which implements JSON literals end to end: a term typed `@json` expands to `{"@value": <raw JSON>, "@type": "@json"}` (arrays included), and `toRdf` emits one `rdf:JSON` literal whose lexical form is the JCS canonicalisation of that JSON. Neither product uses jsonld-java anywhere. The two ends use different Titanium generations (1.6.0 with titanium-jcs 1.0.0 behind Certify, 1.3.1/1.3.2 behind Verify) and different RDF canonicalisers (RDFC-1.0 via titanium-rdfc 2.0.0 behind Certify, URDNA2015 via rdf-urdna 1.2 behind Verify), but the JCS number, string and key handling is the same code on both sides and the N-Quads escaping of a JCS literal is identical, so the signed hash and the verified hash agree. Nothing in Certify's Velocity templating, its document loading or its canonicalisation stringifies, reorders or drops a nested `courses` array. The dependency resolution below is derived from the POMs, not from the jar list inside the images, and no credential with an `@json` term has been issued and verified on the local Compose; section 4 gives the check that would turn "yes from source" into "observed".

## Sources and method

- `mosip/inji-certify` tag `v0.14.0`, `mosip/inji-verify` tag `v0.17.0`, `mosip/vc-verifier` tag `v1.7.0` (the `io.inji:vcverifier-jar` library), `mosip/digital-credential-plugins` tag `v0.6.0` (the mock CSV data provider in the `inji-certify-with-plugins` image), all cloned shallowly and read, never built or run.
- Library sources at the tags the POM graph resolves to: `WebOfTrustInfo/ld-signatures-java` `1.0.0`, `1.5.0`, `1.11.0`; `danubetech/data-integrity-java` `1.17.0`; `decentralized-identity/jsonld-common-java` `v0.5.0`, `1.8.0`, `1.14.0`; `filip26/titanium-json-ld` `v1.1.0`, `v1.3.1`, `v1.3.2`, `v1.6.0`; `filip26/titanium-jcs` `v1.0.0`; `filip26/titanium-rdfc` `v2.0.0`; `filip26/titanium-rdf-n-quads` `v1.0.0`; `setl/rdf-urdna` `1.2`, `1.4`; `jsonld-java/jsonld-java` `v0.13.6`.
- POMs fetched from Maven Central (`io.inji:vcverifier-jar:1.7.0`) and from `https://repo.danubetech.com/repository/maven-public/` (the Danubetech artifacts are not on Central; Certify's root POM lists that repository).
- Specs: JSON-LD 1.1 (W3C REC 2020-07-16), JSON-LD 1.1 Processing Algorithms and API (W3C REC 2020-07-16), RDF Dataset Canonicalization RDFC-1.0 (W3C REC 2024-05-21).
- Local, read-only: `vc-stack/docker-compose.yaml` (images `injistack/inji-certify-with-plugins:0.14.0`, `injistack/inji-verify-service:0.17.0`), `vc-stack/certify_init.sql` (the base64 `vc_template` decoded), `vc-stack/config/academic-transcript-context.json`.
- **Not run:** nothing was executed against the Compose stack. See section 4.

## 1. Which libraries sign and verify

### Certify 0.14 (signing)

| Artifact | Version | How it gets there |
| --- | --- | --- |
| `info.weboftrust:ld-signatures-java` | 1.0.0 | Declared in `certify-service/pom.xml` lines 133-146, with `key-formats-java` and `jsonld-common-java` excluded |
| `com.danubetech:data-integrity-java` | 1.17.0 | Declared in `certify-service/pom.xml` lines 148-150 |
| `decentralized-identity:jsonld-common-java` | **1.14.0** | Transitive from `data-integrity-java` 1.17.0 (depth 2). The 0.5.0 pinned in `certify-integration-api/pom.xml` line 21 (property at root `pom.xml` line 106) sits at depth 3 via `certify-core/pom.xml` line 40, so Maven's nearest-wins rule picks 1.14.0 |
| `com.apicatalog:titanium-json-ld` | 1.6.0 | From `jsonld-common-java` 1.14.0's POM |
| `com.apicatalog:titanium-jcs` | 1.0.0 | From `titanium-json-ld` 1.6.0's POM (JCS implementation) |
| `com.apicatalog:titanium-rdfc` | 2.0.0 | From `jsonld-common-java` 1.14.0's POM (RDFC-1.0 canonicaliser, used by `JsonLDObject.normalize`) |
| `com.apicatalog:titanium-rdf-n-quads` | 1.0.0 | From `titanium-json-ld` 1.6.0's POM (N-Quads writer used by both toRdf and titanium-rdfc) |
| `io.setl:rdf-urdna` | 1.4 | From `data-integrity-java` 1.17.0's POM; present on the classpath but not on the Ed25519Signature2020 path (see below) |
| `org.glassfish:jakarta.json` | 2.0.1 | From `jsonld-common-java` 1.14.0's POM |
| `com.github.jsonld-java:jsonld-java` | absent | Not declared in any POM of `inji-certify`, `ld-signatures-java`, `data-integrity-java` or `jsonld-common-java` |

The image `injistack/inji-certify-with-plugins:0.14.0` is the `certify-service-with-plugins` module, which adds `mock-certify-plugin` 0.6.0 (`certify-service-with-plugins/pom.xml` lines 68-69) on top of `certify-service`.

The Ed25519Signature2020 path is the legacy branch of `W3CJsonLD.addProof` (`certify-service/src/main/java/io/mosip/certify/credential/W3CJsonLD.java` lines 113-126): `DataIntegritySuites.findCryptosuitesForJwsAlgorithm("EdDSA")` does not list `Ed25519Signature2020`, so the code takes `ProofGeneratorFactory` → `Ed25519Signature2020ProofGenerator` (line 28: `new URDNA2015Canonicalizer()` from ld-signatures-java) → `CredentialUtils.generateLdProof` (`utils/CredentialUtils.java` lines 56-70: `canonicalizer.canonicalize(vcLdProof, j)` then the keymanager signs the 64-byte hash). The `data-integrity-java` branch (lines 128-141) is only taken for `DataIntegrityProof` cryptosuites. At runtime ld-signatures-java 1.0.0 (compiled against jsonld-common-java 1.0.0) calls `JsonLDObject.normalize("urdna2015")`, and jsonld-common-java 1.14.0 still exposes that signature: it accepts `"urdna2015"` and `"RDFC-1.0"` and routes both to `RdfCanon.create("SHA-256")` from titanium-rdfc (`jsonld-common-java` 1.14.0 `src/main/java/foundation/identity/jsonld/JsonLDObject.java` lines 385-405).

### Verify 0.17 (verifying)

| Artifact | Version | How it gets there |
| --- | --- | --- |
| `info.weboftrust:ld-signatures-java` | 1.11.0 | Declared directly in `verify-service/pom.xml` lines 103-104 (property at root `pom.xml`) |
| `decentralized-identity:jsonld-common-java` | **1.8.0** | Declared directly in `verify-service/pom.xml` lines 108-109; this overrides the 1.12.0 that ld-signatures-java 1.11.0's POM asks for |
| `io.inji:vcverifier-jar` | 1.7.0 | Declared in `verify-service/pom.xml` lines 113-114; its Maven Central POM lists `ld-signatures-java` 1.5.0 (loses to 1.11.0), `jsonld-common-java` 1.8.0, `titanium-json-ld-jre8` 1.3.1 |
| `com.apicatalog:titanium-json-ld` | 1.3.2 | From `jsonld-common-java` 1.8.0's POM |
| `com.apicatalog:titanium-json-ld-jre8` | 1.3.1 | From `vcverifier-jar` 1.7.0 (`vc-verifier/kotlin/gradle/libs.versions.toml` line 12 and `vcverifier/build.gradle.kts` lines 53-56, which exclude `titanium-json-ld` from ld-signatures-java and add the jre8 artifact). Different artifactId, same packages, so both jars are on the classpath |
| `io.setl:rdf-urdna` | 1.2 | From `jsonld-common-java` 1.8.0's POM (URDNA2015) |
| `org.glassfish:jakarta.json` | 2.0.1 | From `jsonld-common-java` 1.8.0's POM |
| `com.github.jsonld-java:jsonld-java` | absent | Not declared in any POM or Gradle file on this path |

`verify-service` creates `new CredentialsVerifier()` (`verify-service/src/main/java/io/inji/verify/config/AppConfig.java` lines 14-16) and the `ldp_vc` path ends in `vc-verifier/kotlin/vcverifier/src/main/java/io/mosip/vercred/vcverifier/credentialverifier/verifier/LdpVerifier.kt`: it sets a `ConfigurableDocumentLoader` on the credential (line 35-37), builds `URDNA2015Canonicalizer()` from ld-signatures-java and calls `canonicalize(ldProof, vcJsonLdObject)` (lines 42-43), then for a `proofValue` proof multibase-decodes it and checks it with `ED25519SignatureVerifierImpl` (lines 58-62). `URDNA2015Canonicalizer` is byte-for-byte the same 52-line class in ld-signatures-java 1.0.0 and 1.11.0 (`src/main/java/info/weboftrust/ldsignatures/canonicalizer/URDNA2015Canonicalizer.java`): proof options without proof values, document without proof, each normalised with `"urdna2015"`, each SHA-256'd, concatenated. In jsonld-common-java 1.8.0 `normalize("urdna2015")` is `toDataset()` (Titanium `JsonLd.toRdf` with `ordered=true`) followed by `io.setl.rdf.normalization.RdfNormalize.normalize(dataset, algorithm)` and the Titanium `NQuadsWriter` (`JsonLDObject.java` lines 313-326 and 352-360).

So the two ends share the hashing recipe and differ only in the Titanium generation and in which RDF canonicaliser produces the sorted N-Quads.

## 2. Does each library implement `@json`?

### What the specs require

- JSON-LD 1.1 §4.2.2: a term defined with `@type: @json` makes the processor treat the value as a JSON literal; in expanded form it becomes `{"@value": …, "@type": "@json"}`.
- JSON-LD 1.1 §10.2 (`rdf:JSON` datatype): the lexical form must have no unnecessary whitespace, keys ordered lexicographically, and numbers serialised per the ECMAScript rules, i.e. the JCS constraints; JSON-LD 1.1 API §8.6 defines this as the "canonical lexical form" of a JSON literal and §8.2.2 (Object to RDF Conversion) step 8 emits the literal with datatype `rdf:JSON` in that form.
- RDFC-1.0 Appendix B: URDNA2015 is "essentially the same algorithm" as RDFC-1.0; the only change is in the canonical N-Quads escaping of some control characters.

### Titanium (both ends)

Checked in `v1.1.0`, `v1.3.1`, `v1.3.2` and `v1.6.0`:

- Term definition: `@json` is a legal `@type` mapping outside 1.0 mode (`src/main/java/com/apicatalog/jsonld/context/TermDefinitionBuilder.java` lines 248-251 in 1.3.2, 270-273 in 1.6.0). The default `JsonLdOptions` processing mode is `JsonLdVersion.V1_1` (`JsonLdOptions.java` line 139 in 1.3.2, 157 in 1.6.0), and jsonld-common-java never changes it (it only sets `ordered=true`).
- Expansion: a value under a term whose type mapping is `@json` is wrapped as `{"@value": value, "@type": "@json"}` with the raw JSON value, arrays included (`expansion/ObjectExpansion1314.java` lines 710-713 in 1.3.2, 697-700 in 1.6.0, the spec's step 13.6).
- toRdf: when the datatype is `@json`, the value string is `JsonCanonicalizer.canonicalize(value)` and the datatype becomes `rdf:JSON` (`deseralization/ObjectToRdf.java` lines 157-159 in 1.3.2 and 1.3.1; `deseralization/JsonLdToRdf.java` lines 281-283 in 1.6.0, the spec's step 8).
- JCS: 1.1.0, 1.3.1 and 1.3.2 ship the same `com.apicatalog.jsonld.json.JsonCanonicalizer` (identical file, SHA-1 prefix `525657dd`); 1.6.0 deprecates it as a one-line delegate to `com.apicatalog.jcs.JsonCanonicalizer` in titanium-jcs 1.0.0, which cites RFC 8785. The two implementations do the same thing where it matters here: numbers equal to zero print as `0`, magnitudes at or above 1e21 or at or below 1e-21 use the `0E00` exponent form, everything else goes through `DecimalFormat("0.#######")` (1.3.2 `JsonCanonicalizer.java` lines 41-45 and 92-114; titanium-jcs 1.0.0 `src/main/java/com/apicatalog/jcs/JsonCanonicalizer.java` lines 54-56 and 147-169); strings are written with `JsonValue.toString()` of the jakarta.json provider, which is glassfish `jakarta.json` 2.0.1 on both ends; object keys are sorted with `Collections.sort` (1.3.2 `lang/Utils.java` lines 26-35; titanium-jcs lines 221-226). The only divergence is key escaping: 1.3.2 escapes keys with `NQuadsWriter.escape` (tab, backspace, LF, CR, FF, `"`, `\`; `rdf/io/nquad/NQuadsWriter.java` lines 125-152) while titanium-jcs also `\u00xx`-escapes other control characters and DEL (lines 260-297). That only bites a key containing a control character; the `courses` keys (`term`, `courses`, `credits`, `gpa`, `cumGpa`, `no`, `title`, `lec`, `lab`, `grade`) are plain ASCII.

Two caveats on the JCS code, both symmetric across the two ends: `DecimalFormat("0.#######")` rounds to seven fraction digits and is not the ECMAScript shortest-round-trip rule RFC 8785 asks for, so a value such as `3.123456789` would canonicalise to `3.1234568` on both sides (the signature still verifies, but the literal is lossy); and `3.0` canonicalises to `3`, which is what RFC 8785 requires.

### RDF canonicalisation and N-Quads escaping

- Certify: titanium-rdfc 2.0.0 `RdfCanon` consumes quads with the literal value and datatype as strings (`src/main/java/com/apicatalog/rdf/canon/RdfCanon.java` lines 239-247) and serialises them through titanium-rdf-n-quads 1.0.0, whose `NQuadsAlphabet.escape` escapes tab, backspace, LF, CR, FF, `"` and `\` (`src/main/java/com/apicatalog/rdf/nquads/NQuadsAlphabet.java` lines 102-129).
- Verify: rdf-urdna 1.2 `NQuadSerializer.escape` escapes LF, CR, `"` and `\` only (`src/main/java/io/setl/rdf/normalization/NQuadSerializer.java` lines 26-50) and writes `^^<datatype>` (line 97).
- A JCS literal never contains a raw control character (JCS escapes them inside the JSON string), so the `rdf:JSON` literal serialises identically under both writers; `"` and `\`, which a JCS string is full of, are escaped the same way. This is the RDFC-1.0 Appendix B difference and it does not reach a JSON literal. (Aside, unrelated to `@json`: a plain string claim containing a tab would already canonicalise differently between the two stacks today.)

### jsonld-java

Not on either path, confirmed from every POM and Gradle file above. For the record, at its latest tag `v0.13.6` the README still reports conformance against JSON-LD 1.0 only (README lines 275-278), the string `@json` does not occur anywhere under `core/src/main`, and a term's `@type` is accepted only if it is `@id`, `@vocab` or an absolute IRI; anything else, so `@json`, throws `JsonLdError(INVALID_TYPE_MAPPING)` (`core/src/main/java/com/github/jsonldjava/core/Context.java` lines 375-380). A verifier built on jsonld-java would reject a context declaring `@json` outright rather than silently dropping the claim.

## 3. Code paths that could mangle or reject a JSON-literal claim

### Velocity templating in Certify

- The mock CSV data provider puts every cell into an `org.json.JSONObject` as the raw cell string: `jsonObject.put(header, record.get(header))` (`digital-credential-plugins` v0.6.0 `mock-certify-plugin/src/main/java/io/mosip/certify/util/CSVReader.java` lines 35-46). So `courses` arrives as one string holding JSON text.
- `CertifyIssuanceServiceImpl` merges that map into the template parameters (`services/CertifyIssuanceServiceImpl.java` line 253) and runs `toJsonMap` (line 271): a `String` stays a `String` (`JSONObject.wrap`), a `List` becomes a `JSONArray`, a `Map` becomes a `JSONObject` (`utils/CredentialUtils.java` lines 115-143).
- The stack's template splices it unquoted: line 38 of the decoded `vc_template` in `vc-stack/certify_init.sql` reads `"courses": ${courses},`. Velocity 1.7 renders the string verbatim (values are not re-evaluated as templates), and `VelocityTemplatingEngineImpl.format` then parses the whole rendered document once with `new JSONObject(writer.toString())` and returns `jsonObject.toString()` (`vcformatters/VelocityTemplatingEngineImpl.java` lines 240-256). The nested array is parsed into `JSONArray`/`JSONObject` and re-serialised; nothing stringifies it.
- `W3CJsonLD.addProof` parses that string with Jackson into a `Map` (`JsonLDObject.fromJson`, jsonld-common-java 1.14.0 `JsonLDObject.java` line 330) and Titanium receives `Json.createObjectBuilder(map)` (line 412), so the nested structure reaches expansion intact. This is the same path the current, untyped `courses` already takes; the only thing `@json` changes is what expansion does with it.
- Number representation round-trips: Jackson parses `3.75` as a `Double`, glassfish builds the `JsonNumber` from it, JCS formats it; the wallet receives the Jackson serialisation of the same map (`JsonLDObject` is serialised through `@JsonValue getJsonObject()`), and Verify parses it with the same Jackson/jakarta/JCS stack. Integer-valued doubles (`3.0`) and integers (`3`) both canonicalise to `3` on both ends.

### Context loading

- Certify: `W3CJsonLD.addProof` sets the credential's document loader to `null` (`W3CJsonLD.java` line 92), so `toRdfApi()` builds a plain `new JsonLdOptions()` (jsonld-common-java 1.14.0 `JsonLDObject.java` lines 344-351), whose loader is Titanium's `SchemeRouter.defaultInstance()` with `HttpLoader` for `http` and `https` (`titanium-json-ld` 1.6.0 `JsonLdOptions.java` line 144; `loader/SchemeRouter.java` lines 30-32). The document cache is `null` by default and the context cache is created per `JsonLdOptions` instance (`JsonLdOptions.java` lines 175-176), so `http://host.docker.internal:9091/academic-transcript-context.json` is fetched on every signing and a changed context takes effect on the next issuance without a restart. A context carrying `"@type": "@json"` loads exactly like today's: Titanium parses the context in 1.1 mode and the `"@version": 1.1` the file already declares is accepted. The proof's own contexts (`https://w3id.org/security/suites/ed25519-2020/v1`) come from ld-signatures-java's bundled `LDSecurityContexts` loader (`src/main/java/info/weboftrust/ldsignatures/jsonld/LDSecurityContexts.java` lines 21, 46-47, 61; `LdProof.java` line 20).
- Verify: `Util.getConfigurableDocumentLoader()` returns a fresh `ConfigurableDocumentLoader` with `http` and `https` enabled and `file` disabled (`vc-verifier` v1.7.0 `utils/Util.kt` lines 48-56); its local cache starts empty and its remote cache is `null` (jsonld-common-java 1.8.0 `ConfigurableDocumentLoader.java` lines 28-34, 74-115), so the transcript context and the security context are fetched over the network on every verification. Same Titanium parsing, same acceptance of `@json`.

### Canonicalisation and the "one level down" behaviour

- `@json` does not change where a term has to be defined. The type-scoped context in today's `academic-transcript-context.json` still reverts before `credentialSubject` is reached (signing-coverage.md, "The mechanism"), so a `courses` term typed `@json` inside that scoped block would still be dropped by both ends. Option 1a only works together with option 1's lifting of the terms to the top level of the context, which the proposed context at `wiki/schemas/academic-transcript-context.proposed.json` already does.
- Once `courses` is a top-level term typed `@json`, the whole array is one quad `<subject> <ait:courses> "<JCS text>"^^rdf:JSON` on both ends; the ten inner terms need no definitions, and a change to any inner value changes the literal and therefore the hash.
- Nothing on either side rejects the literal: Titanium's only `@json`-related errors are `INVALID_JSON_LITERAL` on the RDF-to-JSON-LD direction, which neither path uses, and the "Datatype […] is not an absolute IRI nor @json" warning, which explicitly exempts `@json` (1.3.2 `ObjectToRdf.java` line 140-141; 1.6.0 `JsonLdToRdf.java` lines 265-266).

## 4. The check that would make this observed

**Observed 2026-10-21**, steps 2 to 5, by `vc-stack/smoke.sh` on the CI stack (GitHub Actions run 39539975939 at commit `506969a`, the context-fix commit): the v1 context served by the `vdr` container through the public gateway, one transcript issued and verified (`SUCCESS`), the copies with a tampered holder id, a tampered `fullName` and a tampered grade inside `courses` each rejected with `ERR_SIGNATURE_VERIFICATION_FAILED`, and no `Cannot load context` or `Datatype […] is not an absolute IRI nor @json` line in the Certify or Verify logs. Step 1 was observed on run 39541706410 (commit `ecddefb`), where `smoke.sh` asserts the `BOOT-INF/lib` entries of `/home/inji/certify-service.jar` and `/home/inji/verify-service.jar`: every version in the table is present on both ends (Certify also carries `titanium-rdf-api` 1.0.0, `titanium-rdf-n-quads` 1.0.0 and `ld-signatures-java` 1.0.0) and neither carries `jsonld-java`. Step 6 (the N-Quads literal) was not run. Smallest version, all inside `vc-stack/` with the stack up:

1. Confirm the resolution in section 1 inside the running images: `docker exec` into the Certify container and `unzip -l` the Spring Boot jar, grepping `BOOT-INF/lib` for `jsonld-common-java`, `titanium-json-ld`, `titanium-jcs`, `titanium-rdfc`, `rdf-urdna`; the same in the Verify container for `jsonld-common-java`, `titanium-json-ld`, `titanium-json-ld-jre8`, `rdf-urdna`, `ld-signatures-java`. Expected: 1.14.0 / 1.6.0 / 1.0.0 / 2.0.0 / 1.4 and 1.8.0 / 1.3.2 / 1.3.1 / 1.2 / 1.11.0.
2. Replace `config/academic-transcript-context.json` with the proposed context (top-level terms, `courses` as `{"@id": "ait:courses", "@type": "@json"}`), served at the same URL. No Certify restart is needed for the signing side (no document cache); follow the repository's existing context-refresh procedure (`context_refresh.sql`, `test_context_refresh.py`) for anything that caches the context elsewhere.
3. Issue one transcript through the usual flow (`smoke.sh` is the pattern) and keep the JSON.
4. POST it to `verify-service`'s `vc-verification` endpoint (`VCVerificationController.java` lines 22 and 27) and expect `SUCCESS`. Check the Certify and Verify logs for `Cannot load context` and for the `Datatype […] is not an absolute IRI nor @json` warning; neither should appear.
5. Change one grade inside `courses` (and separately one top-level claim such as `fullName`) and POST again; expect `ERR_SIGNATURE_VERIFICATION_FAILED` for both, which is the behaviour ticket 03 observed for the VPID context after its terms were lifted.
6. Optional, to see the literal: run jsonld.js `toRDF` with `format: application/n-quads` on the issued credential and confirm exactly one quad with datatype `<http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON>` whose value is the JCS text of `courses`.

If step 1 shows different versions from the table, re-read the relevant parts of section 2 for those versions before trusting steps 4 and 5; the `@json` handling has been in Titanium since before 1.1.0, so an older Titanium would not by itself change the answer, but an unexpected `jsonld-java` would.

## What this means for option 1a

- Option 1a is viable on the stack as deployed: Certify 0.14 will sign the `courses` array as one `rdf:JSON` literal and Verify 0.17 will recompute the same literal. Any tampering inside `courses` is caught, which closes the gap signing-coverage.md describes for the nested course objects without defining the ten inner terms.
- It depends on option 1 being applied at the same time: the `courses` term must be at the top level of the context so it is still in scope at `credentialSubject`.
- Keep `courses` values conservative: ASCII keys, numbers with at most seven fraction digits (grades and credits are fine), and no control characters in strings. All of these are symmetric between the two ends today, but the JCS code is not fully RFC 8785 and a future Titanium upgrade on one side only could change the number formatting for exotic values.
- An outside verifier on jsonld.js or any other JSON-LD 1.1 processor handles the literal the same way; a verifier built on jsonld-java rejects the context with `invalid type mapping`. This is a stronger failure than the silent-drop case in signing-coverage.md, and it is the trade-off against the fallback of defining the inner terms individually, which every processor accepts.
- The verdict above is from source and, since 2026-10-21, observed: section 4's steps 2 to 5 ran green on the CI stack, so option 1a is the context in use (`vc-lab/contexts/transcript/v1.json`).

## Sources

- `mosip/inji-certify` `v0.14.0`: `pom.xml` (line 106 `jsonld.common.java.version`, repository list), `certify-service/pom.xml` (lines 78, 133-150), `certify-core/pom.xml` (line 40), `certify-integration-api/pom.xml` (line 21), `certify-service-with-plugins/pom.xml` (lines 68-69), `certify-service/src/main/java/io/mosip/certify/credential/W3CJsonLD.java`, `…/utils/CredentialUtils.java`, `…/proofgenerators/Ed25519Signature2020ProofGenerator.java`, `…/services/CertifyIssuanceServiceImpl.java`, `…/vcformatters/VelocityTemplatingEngineImpl.java`.
- `mosip/inji-verify` `v0.17.0`: `pom.xml` (version properties), `verify-service/pom.xml` (lines 103-114), `verify-service/src/main/java/io/inji/verify/config/AppConfig.java`, `…/controller/VCVerificationController.java`, `…/services/impl/VCVerificationServiceImpl.java`.
- `mosip/vc-verifier` `v1.7.0`: `vc-verifier/kotlin/gradle/libs.versions.toml`, `vc-verifier/kotlin/vcverifier/build.gradle.kts`, `vc-verifier/kotlin/vcverifier/src/main/java/io/mosip/vercred/vcverifier/credentialverifier/verifier/LdpVerifier.kt`, `…/utils/Util.kt`.
- `mosip/digital-credential-plugins` `v0.6.0`: `mock-certify-plugin/src/main/java/io/mosip/certify/util/CSVReader.java`, `…/service/MockCSVDataProviderPlugin.java`.
- Maven POMs: `https://repo1.maven.org/maven2/io/inji/vcverifier-jar/1.7.0/vcverifier-jar-1.7.0.pom`; `https://repo.danubetech.com/repository/maven-public/info/weboftrust/ld-signatures-java/1.0.0/…` and `…/1.11.0/…`; `…/com/danubetech/data-integrity-java/1.17.0/…`; `…/decentralized-identity/jsonld-common-java/0.5.0/…`, `…/1.8.0/…`, `…/1.14.0/…`.
- `WebOfTrustInfo/ld-signatures-java` `1.0.0` and `1.11.0`: `src/main/java/info/weboftrust/ldsignatures/canonicalizer/URDNA2015Canonicalizer.java`, `…/jsonld/LDSecurityContexts.java`, `…/LdProof.java`.
- `decentralized-identity/jsonld-common-java` `1.8.0` and `1.14.0`: `pom.xml`, `src/main/java/foundation/identity/jsonld/JsonLDObject.java`, `…/ConfigurableDocumentLoader.java`.
- `filip26/titanium-json-ld` `v1.1.0`, `v1.3.1`, `v1.3.2`, `v1.6.0`: `pom.xml`, `src/main/java/com/apicatalog/jsonld/JsonLdOptions.java`, `…/context/TermDefinitionBuilder.java`, `…/expansion/ObjectExpansion1314.java`, `…/deseralization/ObjectToRdf.java` (1.3.x) and `…/deseralization/JsonLdToRdf.java` (1.6.0), `…/json/JsonCanonicalizer.java`, `…/lang/Utils.java`, `…/loader/SchemeRouter.java`, `src/main/java/com/apicatalog/rdf/io/nquad/NQuadsWriter.java`.
- `filip26/titanium-jcs` `v1.0.0`: `src/main/java/com/apicatalog/jcs/JsonCanonicalizer.java`. `filip26/titanium-rdfc` `v2.0.0`: `src/main/java/com/apicatalog/rdf/canon/RdfCanon.java`, `…/Quad.java`. `filip26/titanium-rdf-n-quads` `v1.0.0`: `src/main/java/com/apicatalog/rdf/nquads/NQuadsAlphabet.java`.
- `setl/rdf-urdna` `1.2`: `src/main/java/io/setl/rdf/normalization/NQuadSerializer.java`, `…/RdfNormalize.java`.
- `jsonld-java/jsonld-java` `v0.13.6`: `README.md`, `core/src/main/java/com/github/jsonldjava/core/Context.java`.
- JSON-LD 1.1, W3C Recommendation 2020-07-16, §4.2.2 JSON Literals and §10.2 The `rdf:JSON` Datatype: https://www.w3.org/TR/json-ld11/
- JSON-LD 1.1 Processing Algorithms and API, W3C Recommendation 2020-07-16, §8.2 Object to RDF Conversion and §8.6 Data Round Tripping: https://www.w3.org/TR/json-ld11-api/
- RDF Dataset Canonicalization (RDFC-1.0), W3C Recommendation 2024-05-21, Appendix A (canonical N-Quads) and Appendix B (URDNA2015): https://www.w3.org/TR/rdf-canon/
- Local: `vc-stack/docker-compose.yaml`, `vc-stack/certify_init.sql`, `vc-stack/config/academic-transcript-context.json`, `wiki/schemas/academic-transcript-context.proposed.json`, `wiki/research/signing-coverage.md`.
