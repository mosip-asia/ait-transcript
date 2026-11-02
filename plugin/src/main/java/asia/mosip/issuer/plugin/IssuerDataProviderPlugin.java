package asia.mosip.issuer.plugin;

import io.mosip.certify.api.exception.DataProviderExchangeException;
import io.mosip.certify.api.spi.DataProviderPlugin;
import java.io.IOException;
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
import java.util.function.Function;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Certify's data provider for the Issuer. For each credential request it lists the token's records at the Adapter
 * ({@code GET /records}), asks the Gateway whether the first one passes its Checklist ({@code POST /evaluations}) when
 * the gate is on ({@code mosip.certify.gateway.enabled}), fetches that record ({@code GET /records/{recordId}}) and
 * hands it to Certify shaped for its quoted Velocity template, with the token's {@code sub} and {@code client_id} added
 * as trace keys for the ledger. It knows no claim name, maps no scope, and makes no call until Certify asks for data,
 * so Certify starts whatever is down.
 */
@Component
@ConditionalOnProperty(value = "mosip.certify.integration.data-provider-plugin", havingValue = "IssuerDataProviderPlugin")
public class IssuerDataProviderPlugin implements DataProviderPlugin {

    private static final Logger log = LoggerFactory.getLogger(IssuerDataProviderPlugin.class);
    static final String INVALID_ACCESS_TOKEN = "invalid_access_token";
    static final String NO_RECORD = "no_record";
    static final String ADAPTER_ERROR = "adapter_error";
    static final String GATEWAY_ERROR = "gateway_error";
    /**
     * Keys a record must not carry: Certify's reserved keys, and the trace keys the plugin adds. adapter/openapi.yaml's
     * {@code RecordKey} excludes the same set; adapter/test_adapter.py holds the two equal.
     */
    static final Set<String> FORBIDDEN_KEYS = Set.of("id", "_holderId", "_issuer", "validFrom", "validUntil",
            "credentialStatus", "tokenSub", "tokenClientId");

    /** One HTTP peer: its base URL, a client holding its connect timeout, its read timeout and the code its failures get. */
    private record Peer(String base, HttpClient http, Duration readTimeout, String failure) {
        static Peer of(String url, long connectTimeoutMs, long readTimeoutMs, String failure) {
            HttpClient http = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofMillis(connectTimeoutMs))
                    .build();
            return new Peer(url.replaceAll("/+$", ""), http, Duration.ofMillis(readTimeoutMs), failure);
        }

        /** The answer, or {@link #failure} when the peer cannot be reached or is slower than the read timeout. */
        HttpResponse<String> send(HttpRequest.Builder request) throws DataProviderExchangeException {
            try {
                return http.send(request.timeout(readTimeout).build(), HttpResponse.BodyHandlers.ofString());
            } catch (IOException e) {
                log.warn("{} not reached at {}: {}", failure, base, e.toString());
                throw new DataProviderExchangeException(failure);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new DataProviderExchangeException(failure);
            }
        }

        HttpResponse<String> get(String pathAndQuery) throws DataProviderExchangeException {
            return send(HttpRequest.newBuilder(URI.create(base + pathAndQuery)).GET());
        }
    }

    /** The Approval gate: the Gateway's {@code POST /evaluations}, asked with the shared bearer secret. */
    private record Gate(Peer gateway, String authorization) {
        /** Any 2xx passes; any other answer is refused with its {@code error}. Fails closed. */
        void evaluate(String sub, String scope, String recordId) throws DataProviderExchangeException {
            String body = new JSONObject(Map.of("sub", sub, "scope", scope, "recordId", recordId)).toString();
            HttpResponse<String> response = gateway.send(HttpRequest.newBuilder(URI.create(gateway.base() + "/evaluations"))
                    .header("Authorization", authorization)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body)));
            if (response.statusCode() / 100 != 2) {
                String code = errorCode(response.body());
                log.warn("the Gateway answered {} with error {}", response.statusCode(), code);
                throw new DataProviderExchangeException(code);
            }
        }
    }

    /** What {@code mosip.certify.gateway.url} must say when the gate is off. */
    static final String NO_GATEWAY = "NO GATEWAY";

    private final Peer adapter;
    /** Empty when {@code mosip.certify.gateway.enabled} is false: every record the Adapter serves is issued. */
    private final Optional<Gate> gate;

    /**
     * @throws IllegalArgumentException for a switch that is missing, not {@code true} or {@code false}, or
     *     contradicts the Gateway's URL (on with {@code NO GATEWAY} or no {@code http(s)} URL, off with anything but
     *     {@code NO GATEWAY}), or the gate on without a token; Certify then does not start
     */
    public IssuerDataProviderPlugin(
            @Value("${mosip.certify.adapter.url}") String adapterUrl,
            @Value("${mosip.certify.adapter.connect-timeout-ms:2000}") long adapterConnectTimeoutMs,
            @Value("${mosip.certify.adapter.read-timeout-ms:10000}") long adapterReadTimeoutMs,
            @Value("${mosip.certify.gateway.enabled:}") String gatewayEnabled,
            @Value("${mosip.certify.gateway.url:}") String gatewayUrl,
            @Value("${mosip.certify.gateway.auth-token:}") String gatewayAuthToken,
            @Value("${mosip.certify.gateway.connect-timeout-ms:2000}") long gatewayConnectTimeoutMs,
            @Value("${mosip.certify.gateway.read-timeout-ms:10000}") long gatewayReadTimeoutMs) {
        this.adapter = Peer.of(adapterUrl, adapterConnectTimeoutMs, adapterReadTimeoutMs, ADAPTER_ERROR);
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
                gate.map(g -> g.gateway().base()).orElse(NO_GATEWAY), adapter.base());
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
     * The token's first record, after the Gateway passed it when the gate is on, shaped for Certify's template and
     * extended with {@code tokenSub} and {@code tokenClientId}.
     *
     * @throws DataProviderExchangeException {@code invalid_access_token} for claims without {@code sub}, before any
     *     call; {@code no_record} for an empty list or a 404; the Gateway refusal's {@code error}, else
     *     {@code gateway_error}; {@code adapter_error} for an Adapter that fails or serves a record Certify cannot take
     */
    @Override
    public JSONObject fetchData(Map<String, Object> claims) throws DataProviderExchangeException {
        if (!(claims.get("sub") instanceof String sub) || sub.isEmpty()) {
            throw new DataProviderExchangeException(INVALID_ACCESS_TOKEN);
        }
        String scope = claims.get("scope") instanceof String s ? s : "";
        String recordId = firstRecordId(sub, scope);
        if (gate.isPresent()) {
            gate.get().evaluate(sub, scope, recordId);
        }
        JSONObject record = record(recordId, scope);
        JSONObject data = shape(record);
        data.put("tokenSub", sub);
        if (claims.get("client_id") != null) {
            data.put("tokenClientId", claims.get("client_id"));
        }
        return data;
    }

    /** {@code GET /records?sub=&scope=}: the first entry's {@code recordId}, without selecting. */
    private String firstRecordId(String sub, String scope) throws DataProviderExchangeException {
        HttpResponse<String> response = adapter.get("/records?sub=" + query(sub) + "&scope=" + query(scope));
        JSONArray list = adapterAnswer(response, JSONArray::new);
        if (list.isEmpty()) {
            throw new DataProviderExchangeException(NO_RECORD);
        }
        if (!(list.get(0) instanceof JSONObject first) || !(first.opt("recordId") instanceof String id) || id.isEmpty()) {
            log.warn("the Adapter's list has no recordId in its first entry");
            throw new DataProviderExchangeException(ADAPTER_ERROR);
        }
        return id;
    }

    /** {@code GET /records/{recordId}?scope=}: the record, a JSON object with no forbidden key. */
    private JSONObject record(String recordId, String scope) throws DataProviderExchangeException {
        JSONObject record = adapterAnswer(adapter.get("/records/" + path(recordId) + "?scope=" + query(scope)),
                JSONObject::new);
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
     * except objects and arrays ({@code ${courses}}): every top-level string escaped, every object or array as its
     * JSON text, any other value as it is.
     */
    private static JSONObject shape(JSONObject record) {
        JSONObject data = new JSONObject();
        for (String key : record.keySet()) {
            Object value = record.get(key);
            if (value instanceof String text) {
                data.put(key, escapeForQuotedTemplate(text));
            } else if (value instanceof JSONObject || value instanceof JSONArray) {
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

    private static String query(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private static String path(String segment) {
        return URLEncoder.encode(segment, StandardCharsets.UTF_8).replace("+", "%20");
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
