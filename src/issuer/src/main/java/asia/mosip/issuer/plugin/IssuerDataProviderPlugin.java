package asia.mosip.issuer.plugin;

import io.mosip.certify.api.exception.DataProviderExchangeException;
import io.mosip.certify.api.spi.DataProviderPlugin;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Function;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.json.JSONParserConfiguration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Certify's data provider for the Issuer. For each credential request it asks the Gateway whether the token's student
 * passes the Checklist ({@code POST /evaluations}) when the gate is on ({@code mosip.certify.gateway.enabled}), reads the
 * student's record at the record URL with the token's {@code sub} filled in ({@code mosip.certify.adapter.record-url})
 * and hands it to Certify shaped for its quoted Velocity template, with the token's {@code sub} and {@code client_id}
 * added as trace keys for the ledger. It knows no path, no claim name but {@code courses}, maps no scope, and makes no
 * call until Certify asks for data, so Certify starts whatever is down.
 */
@Component
@ConditionalOnProperty(value = "mosip.certify.integration.data-provider-plugin", havingValue = "IssuerDataProviderPlugin")
public class IssuerDataProviderPlugin implements DataProviderPlugin {

    private static final Logger log = LoggerFactory.getLogger(IssuerDataProviderPlugin.class);
    static final String INVALID_ACCESS_TOKEN = "invalid_access_token";
    static final String NO_RECORD = "no_record";
    static final String ADAPTER_ERROR = "adapter_error";
    static final String GATEWAY_ERROR = "gateway_error";
    /** The one claim a record serves as an array (the contract's terms of courses), which Certify's template takes unquoted. */
    private static final String COURSES = "courses";
    /**
     * Keys a record must not carry: Certify's reserved keys, and the trace keys the plugin adds. adapter/openapi.yaml's
     * {@code RecordKey} excludes the same set; adapter/test_adapter.py holds the two equal.
     */
    static final Set<String> FORBIDDEN_KEYS = Set.of("id", "_holderId", "_issuer", "validFrom", "validUntil",
            "credentialStatus", "tokenSub", "tokenClientId");

    /**
     * One HTTP peer: its URL as configured, a client holding its connect timeout, its read timeout and the code its
     * failures get.
     */
    private record Peer(String url, HttpClient http, Duration readTimeout, String failure) {
        static Peer of(String url, long connectTimeoutMs, long readTimeoutMs, String failure) {
            HttpClient http = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofMillis(connectTimeoutMs))
                    .build();
            return new Peer(url, http, Duration.ofMillis(readTimeoutMs), failure);
        }

        /**
         * The answer, or {@link #failure} when the peer cannot be reached or the whole answer, its body included,
         * takes longer than the read timeout. {@code HttpRequest.timeout} alone stops at the headers.
         */
        HttpResponse<String> send(HttpRequest.Builder request) throws DataProviderExchangeException {
            CompletableFuture<HttpResponse<String>> answer =
                    http.sendAsync(request.timeout(readTimeout).build(), HttpResponse.BodyHandlers.ofString());
            try {
                return answer.get(readTimeout.toMillis(), TimeUnit.MILLISECONDS);
            } catch (ExecutionException | TimeoutException e) {
                answer.cancel(true);
                Throwable cause = e instanceof ExecutionException ? e.getCause() : e;
                log.warn("{} not reached at {}: {}", failure, url, cause.toString());
                throw new DataProviderExchangeException(failure);
            } catch (InterruptedException e) {
                answer.cancel(true);
                Thread.currentThread().interrupt();
                throw new DataProviderExchangeException(failure);
            }
        }
    }

    /** The Approval gate: the Gateway's {@code POST /evaluations}, asked with the shared bearer secret. */
    private record Gate(Peer gateway, String authorization) {
        /**
         * Only a 200 evaluation that lists its checks, each {@code passed: true}, passes. Any other status is refused
         * with its {@code error}, and any other 200 is {@code gateway_error}. Fails closed.
         */
        void evaluate(String sub, String scope) throws DataProviderExchangeException {
            String body = new JSONObject(Map.of("sub", sub, "scope", scope)).toString();
            HttpResponse<String> response = gateway.send(HttpRequest.newBuilder(
                            URI.create(gateway.url().replaceAll("/+$", "") + "/evaluations"))
                    .header("Authorization", authorization)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body)));
            if (response.statusCode() != 200) {
                String code = errorCode(response.body());
                log.warn("the Gateway answered {} with error {}", response.statusCode(), code);
                throw new DataProviderExchangeException(code);
            }
            if (!passes(response.body())) {
                log.warn("the Gateway answered 200 without a passing evaluation");
                throw new DataProviderExchangeException(GATEWAY_ERROR);
            }
        }

        /** An evaluation listing at least one check, each with {@code passed} exactly {@code true}. */
        private static boolean passes(String body) {
            try {
                JSONArray checks = strictObject(body).getJSONArray("checks");
                for (int i = 0; i < checks.length(); i++) {
                    if (!Boolean.TRUE.equals(checks.getJSONObject(i).opt("passed"))) {
                        return false;
                    }
                }
                return !checks.isEmpty();
            } catch (JSONException e) {
                return false;
            }
        }
    }

    private static final JSONParserConfiguration STRICT = new JSONParserConfiguration().withStrictMode();

    /**
     * A JSON object as the contract types the answers: strict JSON only. org.json's lenient forms (unquoted keys or
     * values, single quotes, a trailing comma) and any text after the object throw {@link JSONException}.
     */
    static JSONObject strictObject(String body) {
        return new JSONObject(body, STRICT);
    }

    /** The record URL's placeholder for the token's {@code sub}. */
    static final String SUB = "{sub}";

    /** What {@code mosip.certify.gateway.url} must say when the gate is off. */
    static final String NO_GATEWAY = "NO GATEWAY";

    /** The Adapter, its URL the record URL with {@code {sub}} still in it. */
    private final Peer adapter;
    /** Empty when {@code mosip.certify.gateway.enabled} is false: every record the Adapter serves is issued. */
    private final Optional<Gate> gate;

    /**
     * @throws IllegalArgumentException for a record URL that is not an {@code http(s)} URL holding {@code {sub}}, a
     *     switch that is missing, not {@code true} or {@code false}, or contradicts the Gateway's URL (on with
     *     {@code NO GATEWAY} or no {@code http(s)} URL, off with anything but {@code NO GATEWAY}), or the gate on
     *     without a token; Certify then does not start
     */
    public IssuerDataProviderPlugin(
            @Value("${mosip.certify.adapter.record-url}") String recordUrl,
            @Value("${mosip.certify.adapter.connect-timeout-ms:2000}") long adapterConnectTimeoutMs,
            @Value("${mosip.certify.adapter.read-timeout-ms:10000}") long adapterReadTimeoutMs,
            @Value("${mosip.certify.gateway.enabled:}") String gatewayEnabled,
            @Value("${mosip.certify.gateway.url:}") String gatewayUrl,
            @Value("${mosip.certify.gateway.auth-token:}") String gatewayAuthToken,
            @Value("${mosip.certify.gateway.connect-timeout-ms:2000}") long gatewayConnectTimeoutMs,
            @Value("${mosip.certify.gateway.read-timeout-ms:10000}") long gatewayReadTimeoutMs) {
        if (!recordUrl.contains(SUB) || !isHttpUrl(recordUrl.replace(SUB, "sub"))) {
            throw new IllegalArgumentException("mosip.certify.adapter.record-url must be an http(s) URL holding "
                    + SUB + ", not '" + recordUrl + "'");
        }
        this.adapter = Peer.of(recordUrl, adapterConnectTimeoutMs, adapterReadTimeoutMs, ADAPTER_ERROR);
        boolean enabled = switchSetting(gatewayEnabled);
        if (enabled) {
            if (!isHttpUrl(gatewayUrl)) {
                throw new IllegalArgumentException("mosip.certify.gateway.enabled is true, so mosip.certify.gateway.url "
                        + "must be an http(s) URL, not '" + gatewayUrl + "'");
            }
            if (gatewayAuthToken.isEmpty()) {
                throw new IllegalArgumentException(
                        "mosip.certify.gateway.enabled is true, so mosip.certify.gateway.auth-token is required");
            }
            this.gate = Optional.of(new Gate(Peer.of(gatewayUrl, gatewayConnectTimeoutMs, gatewayReadTimeoutMs,
                    GATEWAY_ERROR), "Bearer " + gatewayAuthToken));
        } else {
            if (!NO_GATEWAY.equals(gatewayUrl)) {
                throw new IllegalArgumentException("mosip.certify.gateway.enabled is false, so mosip.certify.gateway.url "
                        + "must be '" + NO_GATEWAY + "', not '" + gatewayUrl + "'");
            }
            this.gate = Optional.empty();
        }
        log.info("IssuerDataProviderPlugin selected: gateway.enabled={}, Gateway {}, Adapter {}", enabled,
                gate.map(g -> g.gateway().url()).orElse(NO_GATEWAY), adapter.url());
    }

    /** {@code mosip.certify.gateway.enabled}: exactly {@code true} or {@code false}, with no default. */
    private static boolean switchSetting(String value) {
        if ("true".equals(value) || "false".equals(value)) {
            return Boolean.parseBoolean(value);
        }
        throw new IllegalArgumentException("mosip.certify.gateway.enabled is required and must be true or false, not '"
                + value + "'");
    }

    private static boolean isHttpUrl(String value) {
        try {
            URI uri = new URI(value);
            return ("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) && uri.getHost() != null;
        } catch (URISyntaxException e) {
            return false;
        }
    }

    /**
     * The token's student's record, after the Gateway passed the student when the gate is on, shaped for Certify's
     * template and extended with {@code tokenSub} and {@code tokenClientId}.
     *
     * @throws DataProviderExchangeException {@code invalid_access_token} for claims without {@code sub}, before any
     *     call; the Gateway refusal's {@code error}, else {@code gateway_error}, before the record is read;
     *     {@code no_record} for a 404; {@code adapter_error} for an Adapter that fails or serves a record Certify
     *     cannot take
     */
    @Override
    public JSONObject fetchData(Map<String, Object> claims) throws DataProviderExchangeException {
        if (!(claims.get("sub") instanceof String sub) || sub.isEmpty()) {
            throw new DataProviderExchangeException(INVALID_ACCESS_TOKEN);
        }
        if (gate.isPresent()) {
            gate.get().evaluate(sub, claims.get("scope") instanceof String scope ? scope : "");
        }
        JSONObject record = record(sub);
        JSONObject data = shape(record);
        data.put("tokenSub", sub);
        if (claims.get("client_id") != null) {
            data.put("tokenClientId", claims.get("client_id"));
        }
        return data;
    }

    /** The record URL with {@code sub} filled in as one path segment: the record, a JSON object with no forbidden key. */
    private JSONObject record(String sub) throws DataProviderExchangeException {
        URI uri = URI.create(adapter.url().replace(SUB, pathSegment(sub)));
        JSONObject record = adapterAnswer(adapter.send(HttpRequest.newBuilder(uri).GET()),
                IssuerDataProviderPlugin::strictObject);
        for (String key : record.keySet()) {
            if (FORBIDDEN_KEYS.contains(key)) {
                log.warn("the Adapter's record carries the forbidden key {}", key);
                throw new DataProviderExchangeException(ADAPTER_ERROR);
            }
        }
        return record;
    }

    /** A 200's body parsed, {@code no_record} for a 404, {@code adapter_error} for anything else. */
    private static <T> T adapterAnswer(HttpResponse<String> response, Function<String, T> parser)
            throws DataProviderExchangeException {
        if (response.statusCode() == 404) {
            throw new DataProviderExchangeException(NO_RECORD);
        }
        if (response.statusCode() != 200) {
            log.warn("the Adapter answered {}", response.statusCode());
            throw new DataProviderExchangeException(ADAPTER_ERROR);
        }
        try {
            return parser.apply(response.body());
        } catch (JSONException e) {
            log.warn("the Adapter's answer is not the expected JSON: {}", e.getMessage());
            throw new DataProviderExchangeException(ADAPTER_ERROR);
        }
    }

    /**
     * The record for Certify's template, which substitutes every claim into a quoted slot ({@code "${fullName}"})
     * except {@code courses} ({@code ${courses}}): every top-level string escaped, {@code courses} as its JSON text,
     * any other value as it is. The contract allows no other object or array at the top, and a {@code courses} that is
     * not an array would reach the unquoted slot as something else, so both are {@code adapter_error}; so is a
     * {@code null}, which Certify would sign as the template's literal placeholder.
     */
    private static JSONObject shape(JSONObject record) throws DataProviderExchangeException {
        JSONObject data = new JSONObject();
        for (String key : record.keySet()) {
            Object value = record.get(key);
            if (value == JSONObject.NULL) {
                log.warn("the Adapter's record has null for {}", key);
                throw new DataProviderExchangeException(ADAPTER_ERROR);
            }
            boolean structured = value instanceof JSONObject || value instanceof JSONArray;
            if (COURSES.equals(key) ? !(value instanceof JSONArray) : structured) {
                log.warn("the Adapter's record has a {} for {}", value.getClass().getSimpleName(), key);
                throw new DataProviderExchangeException(ADAPTER_ERROR);
            }
            if (value instanceof String text) {
                data.put(key, escapeForQuotedTemplate(text));
            } else if (structured) {
                data.put(key, value.toString());
            } else {
                data.put(key, value);
            }
        }
        return data;
    }

    /**
     * JSON string escaping without the surrounding quotes, ASCII only, as Python's {@code json.dumps(value)[1:-1]}
     * writes it: a quote or a backslash gets a backslash before it, newline, carriage return, tab, backspace and form
     * feed get their short escapes, and every other character outside printable ASCII becomes a backslash, a
     * {@code u} and its four hex digits (per UTF-16 code unit, so a surrogate pair is two escapes).
     */
    static String escapeForQuotedTemplate(String value) {
        StringBuilder out = new StringBuilder(value.length());
        for (char c : value.toCharArray()) {
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                default -> {
                    if (c < 0x20 || c > 0x7e) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.toString();
    }

    private static String pathSegment(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    /** The {@code error} string of a refusal's JSON body, else {@code gateway_error}. */
    private static String errorCode(String body) {
        try {
            String error = new JSONObject(body).optString("error");
            return error.isEmpty() ? GATEWAY_ERROR : error;
        } catch (JSONException e) {
            return GATEWAY_ERROR;
        }
    }
}
