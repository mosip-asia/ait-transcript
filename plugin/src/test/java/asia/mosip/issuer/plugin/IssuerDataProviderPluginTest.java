package asia.mosip.issuer.plugin;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.sun.net.httpserver.HttpServer;
import io.mosip.certify.api.exception.DataProviderExchangeException;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * The plugin against a stand-in Adapter and a stand-in Gateway on local ports: the requests each one receives, in
 * order, and the data map or error code the plugin hands Certify.
 */
class IssuerDataProviderPluginTest {

    private static final String TOKEN = "test-token";
    /** A space and a slash: the plugin must fill it into the record URL as one path segment. */
    private static final String SUB = "st 123/456";
    private static final String SCOPE = "openid ait_transcript_vc_ldp";
    /** The record URL's path, as an Installation sets it. */
    private static final String RECORD_URL_PATH = "/student/{sub}/transcript";
    private static final String RECORD_PATH = "/student/st%20123%2F456/transcript";
    private static final String ADAPTER_RECORD_URL = "http://adapter:8000/student/{sub}/transcript";
    private static final Map<String, Object> CLAIMS = Map.of("sub", SUB, "scope", SCOPE, "client_id", "smoke",
            "accessTokenHash", "h4sh", "iss", "http://keycloak:8080/realms/inji");

    /** One request as a stand-in saw it, the query decoded. */
    record Seen(String server, String method, String path, Map<String, String> query, String authorization,
            String contentType, String body) {}

    record Reply(int status, String body, long delayMs) {
        static Reply of(int status, String body) {
            return new Reply(status, body, 0);
        }
    }

    /** Every request either stand-in received, in arrival order. */
    private final List<Seen> seen = new CopyOnWriteArrayList<>();
    private final Map<String, Reply> adapterReplies = new ConcurrentHashMap<>();
    private final Map<String, Reply> gatewayReplies = new ConcurrentHashMap<>();
    private final List<HttpServer> servers = new CopyOnWriteArrayList<>();

    /** A server on a local port answering each path from {@code replies}, 599 for any other path. */
    private String standIn(String name, Map<String, Reply> replies) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            String path = exchange.getRequestURI().getRawPath();
            seen.add(new Seen(name, exchange.getRequestMethod(), path, query(exchange.getRequestURI().getRawQuery()),
                    exchange.getRequestHeaders().getFirst("Authorization"),
                    exchange.getRequestHeaders().getFirst("Content-Type"),
                    new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)));
            Reply reply = replies.getOrDefault(path, Reply.of(599, "no reply for " + path));
            try {
                Thread.sleep(reply.delayMs());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            byte[] bytes = reply.body().getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(reply.status(), bytes.length == 0 ? -1 : bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        servers.add(server);
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    private static Map<String, String> query(String raw) {
        Map<String, String> query = new LinkedHashMap<>();
        if (raw != null) {
            for (String pair : raw.split("&")) {
                String[] kv = pair.split("=", 2);
                query.put(URLDecoder.decode(kv[0], StandardCharsets.UTF_8),
                        URLDecoder.decode(kv.length > 1 ? kv[1] : "", StandardCharsets.UTF_8));
            }
        }
        return query;
    }

    /** The gate on, the record read at {@link #RECORD_URL_PATH} on {@code adapter}. */
    private IssuerDataProviderPlugin plugin(String adapter, long adapterReadMs, String gatewayUrl, long gatewayReadMs) {
        return new IssuerDataProviderPlugin(adapter + RECORD_URL_PATH, 2000, adapterReadMs, "true", gatewayUrl, TOKEN,
                2000, gatewayReadMs);
    }

    /** The gate off, configured as an Installation run without the Gateway is: no token, no timeouts. */
    private IssuerDataProviderPlugin gateOff(String adapter) {
        return new IssuerDataProviderPlugin(adapter + RECORD_URL_PATH, 2000, 10000, "false", "NO GATEWAY", "", 2000,
                10000);
    }

    /** The happy answers: a pass, then the record. */
    {
        adapterReplies.put(RECORD_PATH, Reply.of(200, "{\"fullName\": \"Somchai Jaidee\"}"));
        gatewayReplies.put("/evaluations", Reply.of(200,
                "{\"credentialType\": \"AitTranscriptCredential\", \"checks\": [{\"check\": \"no_holds\", \"passed\": true}]}"));
    }

    /** Both stand-ins up. */
    private IssuerDataProviderPlugin plugin() throws IOException {
        return plugin(10000, 10000);
    }

    private IssuerDataProviderPlugin plugin(long adapterReadMs, long gatewayReadMs) throws IOException {
        return plugin(standIn("adapter", adapterReplies), adapterReadMs, standIn("gateway", gatewayReplies), gatewayReadMs);
    }

    @AfterEach
    void stop() {
        servers.forEach(server -> server.stop(0));
    }

    private Seen recordRequest() {
        return new Seen("adapter", "GET", RECORD_PATH, Map.of(), null, null, "");
    }

    private static DataProviderExchangeException refused(IssuerDataProviderPlugin plugin, Map<String, Object> claims) {
        return assertThrows(DataProviderExchangeException.class, () -> plugin.fetchData(claims));
    }

    @Test
    void aPassEvaluatesThenFetchesAndReturnsTheRecordEscapedAndExtended() throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        adapterReplies.put(RECORD_PATH, Reply.of(200, """
                {"fullName": "Somchai \\"Tom\\" Jaidée",
                 "programCommittee": "Prof. A (Chair)\\nDr. B",
                 "courses": [{"term": "2025/1", "courses": [{"no": "CS601", "grade": "A"}]}],
                 "totalCredits": "48",
                 "credits": 48,
                 "conferred": true}"""));

        JSONObject data = plugin.fetchData(CLAIMS);

        assertEquals(2, seen.size(), seen.toString());
        Seen evaluation = seen.get(0);
        assertEquals(List.of("gateway", "POST", "/evaluations", "Bearer " + TOKEN, "application/json"),
                List.of(evaluation.server(), evaluation.method(), evaluation.path(), evaluation.authorization(),
                        evaluation.contentType()));
        assertEquals(Map.of("sub", SUB, "scope", SCOPE), new JSONObject(evaluation.body()).toMap());
        assertEquals(recordRequest(), seen.get(1));

        Map<String, Object> expected = new HashMap<>();
        expected.put("fullName", "Somchai \\\"Tom\\\" Jaid\\u00e9e");
        expected.put("programCommittee", "Prof. A (Chair)\\nDr. B");
        expected.put("totalCredits", "48");
        expected.put("credits", 48);
        expected.put("conferred", true);
        expected.put("tokenSub", SUB);
        expected.put("tokenClientId", "smoke");
        Map<String, Object> got = new HashMap<>(data.toMap());
        // courses reaches the template as its JSON text (key order inside it is not significant).
        assertEquals(List.of(Map.of("term", "2025/1", "courses", List.of(Map.of("no", "CS601", "grade", "A")))),
                new JSONArray((String) got.remove("courses")).toList());
        assertEquals(expected, got);
    }

    @Test
    void aTokenWithoutAClientIdGetsNoTokenClientId() throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        Map<String, Object> nullClient = new HashMap<>(Map.of("sub", SUB, "scope", SCOPE));
        nullClient.put("client_id", null);

        for (Map<String, Object> claims : List.of(Map.<String, Object>of("sub", SUB, "scope", SCOPE), nullClient)) {
            assertEquals(Map.of("fullName", "Somchai Jaidee", "tokenSub", SUB), plugin.fetchData(claims).toMap());
        }
    }

    /** Every top-level string reaches Certify escaped as Python's json.dumps writes it, without the quotes. */
    @Test
    void quotesNewlinesAndNonAsciiAreEscapedForTheQuotedTemplate() throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        String value = "a\"b\\c\n\r\t\b\f\u0001\u007f é ü 中 😀 </   ${x} #if";
        adapterReplies.put(RECORD_PATH, Reply.of(200, new JSONObject(Map.of("fullName", value)).toString()));

        String escaped = (String) plugin.fetchData(CLAIMS).get("fullName");

        // The literal json.dumps(value)[1:-1] prints.
        assertEquals("a\\\"b\\\\c\\n\\r\\t\\b\\f\\u0001\\u007f \\u00e9 \\u00fc \\u4e2d \\ud83d\\ude00 </ \\u2028 ${x} #if",
                escaped);
        // Substituted into the template's quoted slot, it reads back as the Adapter's value.
        assertEquals(value, new JSONObject("{\"fullName\": \"" + escaped + "\"}").getString("fullName"));
    }

    @ParameterizedTest(name = "{0} {1} -> {2}")
    @CsvSource(delimiter = '|', textBlock = """
            403 | {"error": "checklist_failed", "credentialType": "AitTranscriptCredential", "checks": []} | checklist_failed
            404 | {"error": "no_record"}                                                                   | no_record
            400 | {"error": "unknown_scope"}                                                               | unknown_scope
            502 | {"error": "gateway_error"}                                                               | gateway_error
            401 | {"detail": "missing or wrong bearer token"}                                              | gateway_error
            500 | Internal Server Error                                                                    | gateway_error
            503 | ''                                                                                       | gateway_error
            """)
    void aGatewayRefusalIsForwardedAndTheRecordIsNeverFetched(int status, String body, String code) throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        gatewayReplies.put("/evaluations", Reply.of(status, body));

        assertEquals(code, refused(plugin, CLAIMS).getErrorCode());
        assertEquals(List.of("/evaluations"), seen.stream().map(Seen::path).toList());
    }

    @ParameterizedTest
    @CsvSource({"http://127.0.0.1:1", "http://gateway.invalid:8000"})
    void aGatewayThatCannotBeReachedIsGatewayErrorAndTheRecordIsNeverFetched(String gatewayUrl) throws Exception {
        IssuerDataProviderPlugin plugin = plugin(standIn("adapter", adapterReplies), 10000, gatewayUrl, 10000);

        assertEquals("gateway_error", refused(plugin, CLAIMS).getErrorCode());
        assertEquals(List.of(), seen);
    }

    @Test
    void aGatewaySlowerThanItsReadTimeoutIsGatewayErrorAndTheRecordIsNeverFetched() throws Exception {
        IssuerDataProviderPlugin plugin = plugin(10000, 200);
        gatewayReplies.put("/evaluations", new Reply(200, "{}", 1000));

        long start = System.nanoTime();
        assertEquals("gateway_error", refused(plugin, CLAIMS).getErrorCode());
        assertTrue(System.nanoTime() - start < 800_000_000L, "the read timeout did not cut the call short");
        assertEquals(List.of("/evaluations"), seen.stream().map(Seen::path).toList());
    }

    /** Keycloak always puts sub in its tokens, so the stack cannot produce this case; only this test covers it. */
    @Test
    void claimsWithoutSubAreInvalidAccessTokenAndNothingIsCalled() throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        Map<String, Object> blankSub = new HashMap<>(Map.of("sub", "", "scope", SCOPE));
        Map<String, Object> nullSub = new HashMap<>(Map.of("scope", SCOPE));
        nullSub.put("sub", null);

        for (Map<String, Object> claims : List.of(Map.<String, Object>of("scope", SCOPE), blankSub, nullSub)) {
            assertEquals("invalid_access_token", refused(plugin, claims).getErrorCode(), claims.toString());
        }
        assertEquals(List.of(), seen);
    }

    @ParameterizedTest(name = "{0}")
    @CsvSource(delimiter = '|', textBlock = """
            a 404           | {"detail": "no such student"}
            a 404, no body  | ''
            """)
    void aRecordThatAnswers404IsNoRecord(String name, String body) throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        adapterReplies.put(RECORD_PATH, Reply.of(404, body));

        assertEquals("no_record", refused(plugin, CLAIMS).getErrorCode());
        assertEquals(List.of("/evaluations", RECORD_PATH), seen.stream().map(Seen::path).toList());
    }

    /** The deployment owns the whole URL: any path, a query included; the plugin only fills in {@code {sub}}. */
    @Test
    void theRecordIsReadAtWhateverUrlTheInstallationSets() throws Exception {
        String adapter = standIn("adapter", adapterReplies);
        adapterReplies.put("/api/v2/st%20123%2F456", Reply.of(200, "{\"fullName\": \"Somchai Jaidee\"}"));

        new IssuerDataProviderPlugin(adapter + "/api/v2/{sub}?type=transcript", 2000, 10000, "false", "NO GATEWAY", "",
                2000, 10000).fetchData(CLAIMS);

        assertEquals(List.of(new Seen("adapter", "GET", "/api/v2/st%20123%2F456", Map.of("type", "transcript"), null,
                null, "")), seen);
    }

    @ParameterizedTest(name = "the record answers {0}")
    @CsvSource(delimiter = '|', textBlock = """
            another status  | 503 | {"fullName": "Somchai Jaidee"}
            an array        | 200 | [{"fullName": "Somchai Jaidee"}]
            a string        | 200 | "Somchai Jaidee"
            not JSON        | 200 | not json
            no body         | 200 | ''
            """)
    void aRecordThatIsNotAJsonObjectIsAdapterError(String name, int status, String body) throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        adapterReplies.put(RECORD_PATH, Reply.of(status, body));

        assertEquals("adapter_error", refused(plugin, CLAIMS).getErrorCode());
        assertEquals(List.of("/evaluations", RECORD_PATH), seen.stream().map(Seen::path).toList());
    }

    @ParameterizedTest
    @ValueSource(strings = {"id", "_holderId", "_issuer", "validFrom", "validUntil", "credentialStatus", "tokenSub",
            "tokenClientId"})
    void aRecordCarryingAReservedOrTraceKeyIsAdapterError(String key) throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        adapterReplies.put(RECORD_PATH, Reply.of(200, new JSONObject(Map.of("fullName", "Somchai Jaidee", key, "x")).toString()));

        assertEquals("adapter_error", refused(plugin, CLAIMS).getErrorCode());
    }

    /** `courses` is the one array the contract allows at the top of a record; any other extra field is a scalar. */
    @ParameterizedTest(name = "the record carries {0}")
    @CsvSource(delimiter = '|', textBlock = """
            an object                  | {"fullName": "Somchai Jaidee", "committee": {"chair": "Dr. A"}}
            an array                   | {"fullName": "Somchai Jaidee", "tags": ["a", "b"]}
            courses as a string        | {"fullName": "Somchai Jaidee", "courses": "CS601"}
            courses as an object       | {"fullName": "Somchai Jaidee", "courses": {"term": "2025/1"}}
            courses as null            | {"fullName": "Somchai Jaidee", "courses": null}
            """)
    void aRecordWithAnObjectOrArrayOtherThanCoursesOrCoursesThatIsNotAnArrayIsAdapterError(String name, String body)
            throws Exception {
        IssuerDataProviderPlugin plugin = plugin();
        adapterReplies.put(RECORD_PATH, Reply.of(200, body));

        assertEquals("adapter_error", refused(plugin, CLAIMS).getErrorCode());
    }

    @ParameterizedTest
    @CsvSource({"http://127.0.0.1:1", "http://adapter.invalid:8000"})
    void anAdapterThatCannotBeReachedIsAdapterError(String adapter) throws Exception {
        IssuerDataProviderPlugin plugin = plugin(adapter, 10000, standIn("gateway", gatewayReplies), 10000);

        assertEquals("adapter_error", refused(plugin, CLAIMS).getErrorCode());
        assertEquals(List.of("/evaluations"), seen.stream().map(Seen::path).toList());
    }

    @Test
    void anAdapterSlowerThanItsReadTimeoutIsAdapterError() throws Exception {
        IssuerDataProviderPlugin plugin = plugin(200, 10000);
        adapterReplies.computeIfPresent(RECORD_PATH, (p, reply) -> new Reply(reply.status(), reply.body(), 1000));

        long start = System.nanoTime();
        assertEquals("adapter_error", refused(plugin, CLAIMS).getErrorCode());
        assertTrue(System.nanoTime() - start < 800_000_000L, "the read timeout did not cut the call short");
    }

    @Test
    void makesNoCallUntilAskedForData() throws Exception {
        plugin();
        gateOff(standIn("adapter", adapterReplies));
        assertEquals(List.of(), seen);
    }

    // ---------- the gate off ----------

    @Test
    void withTheGateOffTheGatewayIsNeverCalledEvenWhenOneListensAndTheResultIsTheGateOnOne() throws Exception {
        String adapterUrl = standIn("adapter", adapterReplies);
        JSONObject gateOn = plugin(adapterUrl, 10000, standIn("gateway", gatewayReplies), 10000).fetchData(CLAIMS);
        seen.clear();
        // The Gateway still listens, and would now refuse: with the gate off nothing asks it.
        gatewayReplies.put("/evaluations", Reply.of(403, "{\"error\": \"checklist_failed\"}"));

        JSONObject gateOff = gateOff(adapterUrl).fetchData(CLAIMS);

        assertEquals(gateOn.toMap(), gateOff.toMap());
        assertEquals(List.of(recordRequest()), seen);
    }

    @ParameterizedTest(name = "the record answers {0}")
    @CsvSource(delimiter = '|', textBlock = """
            a 404           | 404 | ''                        | no_record
            another status  | 500 | {"fullName": "Somchai"}   | adapter_error
            an array        | 200 | [{"fullName": "Somchai"}] | adapter_error
            """)
    void withTheGateOffTheAdaptersRefusalsAreTheGateOnOnes(String name, int status, String body, String code)
            throws Exception {
        adapterReplies.put(RECORD_PATH, Reply.of(status, body));

        assertEquals(code, refused(gateOff(standIn("adapter", adapterReplies)), CLAIMS).getErrorCode());
        assertEquals(List.of(recordRequest()), seen);
    }

    @Test
    void withTheGateOffAnAdapterThatCannotBeReachedIsAdapterError() {
        assertEquals("adapter_error", refused(gateOff("http://127.0.0.1:1"), CLAIMS).getErrorCode());
    }

    // ---------- the record URL: a bad one throws at construction, so Certify does not start ----------

    @ParameterizedTest(name = "record url ''{0}''")
    @ValueSource(strings = {"", "http://adapter:8000/student/transcript", "adapter:8000/student/{sub}/transcript",
            "ftp://adapter:8000/student/{sub}/transcript", "http:///student/{sub}/transcript",
            "http://ad apter:8000/student/{sub}/transcript"})
    void aRecordUrlThatIsNotHttpOrHoldsNoSubThrowsAtConstruction(String url) {
        IllegalArgumentException e = assertThrows(IllegalArgumentException.class,
                () -> new IssuerDataProviderPlugin(url, 2000, 10000, "false", "NO GATEWAY", "", 2000, 10000));
        assertTrue(e.getMessage().contains("mosip.certify.adapter.record-url"), e.getMessage());
    }

    // ---------- the switch: a bad setting throws at construction, so Certify does not start ----------

    @ParameterizedTest(name = "enabled={0} url={1} token={2}")
    @CsvSource(delimiter = '|', textBlock = """
            ''    | http://gateway:8000 | t
            yes   | http://gateway:8000 | t
            TRUE  | http://gateway:8000 | t
            1     | http://gateway:8000 | t
            on    | NO GATEWAY          | ''
            true  | NO GATEWAY          | t
            false | http://gateway:8000 | ''
            true  | ''                  | t
            false | ''                  | ''
            false | no gateway          | ''
            true  | gateway:8000        | t
            true  | ftp://gateway:8000  | t
            true  | http://             | t
            true  | http://gateway:8000 | ''
            """)
    void aMissingNonBooleanOrContradictorySwitchThrowsAtConstruction(String enabled, String url, String token) {
        assertThrows(IllegalArgumentException.class,
                () -> new IssuerDataProviderPlugin(ADAPTER_RECORD_URL, 2000, 10000, enabled, url, token, 2000, 10000));
    }

    @ParameterizedTest(name = "enabled={0} url={1}")
    @CsvSource(delimiter = '|', textBlock = """
            true  | http://gateway:8000
            true  | https://gateway.example/
            false | NO GATEWAY
            """)
    void aConsistentSwitchConstructs(String enabled, String url) {
        new IssuerDataProviderPlugin(ADAPTER_RECORD_URL, 2000, 10000, enabled, url, enabled.equals("true") ? TOKEN : "",
                2000, 10000);
    }
}
