package asia.mosip.issuer.gateway.plugin;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.sun.net.httpserver.HttpServer;
import io.mosip.certify.api.exception.DataProviderExchangeException;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

/** The plugin against a stand-in Gateway on a local port: what it sends, and what it makes of each answer. */
class GatewayDataProviderPluginTest {

    private static final String TOKEN = "test-token";

    /** One request as the stand-in Gateway saw it. */
    record Seen(String method, String path, String authorization, String contentType, String body) {}

    private final List<Seen> seen = new CopyOnWriteArrayList<>();
    private HttpServer server;
    private int status = 200;
    private String answer = "{}";
    private long delayMs = 0;

    private GatewayDataProviderPlugin plugin(long readTimeoutMs) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            seen.add(new Seen(exchange.getRequestMethod(), exchange.getRequestURI().getPath(),
                    exchange.getRequestHeaders().getFirst("Authorization"),
                    exchange.getRequestHeaders().getFirst("Content-Type"),
                    new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)));
            try {
                Thread.sleep(delayMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            byte[] bytes = answer.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length == 0 ? -1 : bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        return new GatewayDataProviderPlugin("http://127.0.0.1:" + server.getAddress().getPort(), TOKEN, 2000, readTimeoutMs);
    }

    private GatewayDataProviderPlugin plugin() throws IOException {
        return plugin(10000);
    }

    @AfterEach
    void stop() {
        if (server != null) server.stop(0);
    }

    @Test
    void postsTheTokenClaimsMinusAccessTokenHashWithTheBearerToken() throws Exception {
        plugin().fetchData(Map.of("sub", "ait-2026-0001", "scope", "openid ait_transcript_vc_ldp",
                "client_id", "wallet-demo", "accessTokenHash", "h4sh"));

        assertEquals(1, seen.size());
        Seen request = seen.get(0);
        assertEquals("POST", request.method());
        assertEquals("/issuances", request.path());
        assertEquals("Bearer " + TOKEN, request.authorization());
        assertEquals("application/json", request.contentType());
        assertEquals(Map.of("sub", "ait-2026-0001", "scope", "openid ait_transcript_vc_ldp", "client_id", "wallet-demo"),
                new JSONObject(request.body()).toMap());
    }

    @Test
    void turnsEveryTopLevelObjectAndArrayIntoItsJsonTextAndKeepsTheRest() throws Exception {
        GatewayDataProviderPlugin plugin = plugin();
        answer = """
                {"fullName": "Somchai \\\\\\"Tom\\\\\\" Jaidee",
                 "courses": [{"term": "2025/1", "courses": [{"code": "CS601", "grade": "A"}]}],
                 "committee": {"chair": "Dr. A"},
                 "totalCredits": "48"}""";

        JSONObject claims = plugin.fetchData(Map.of("sub", "ait-2026-0001", "scope", "ait_transcript_vc_ldp"));

        assertEquals(Set.of("fullName", "courses", "committee", "totalCredits"), claims.keySet());
        assertEquals("Somchai \\\"Tom\\\" Jaidee", claims.get("fullName"));
        assertEquals("48", claims.get("totalCredits"));
        // Certify's template receives text; the text is the same JSON (key order inside it is not significant).
        assertEquals(List.of(Map.of("term", "2025/1", "courses", List.of(Map.of("code", "CS601", "grade", "A")))),
                new JSONArray((String) claims.get("courses")).toList());
        assertEquals(Map.of("chair", "Dr. A"), new JSONObject((String) claims.get("committee")).toMap());
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
            200 | not json                                                                                 | gateway_error
            """)
    void anAnswerOtherThanAClaimSetIsAnExchangeErrorWithTheBodysErrorElseGatewayError(
            int status, String body, String code) throws Exception {
        GatewayDataProviderPlugin plugin = plugin();
        this.status = status;
        this.answer = body;

        DataProviderExchangeException e = assertThrows(DataProviderExchangeException.class,
                () -> plugin.fetchData(Map.of("sub", "ait-2026-0002", "scope", "ait_transcript_vc_ldp")));
        assertEquals(code, e.getErrorCode());
    }

    @ParameterizedTest
    @CsvSource({"http://127.0.0.1:1", "http://gateway.invalid:8000"})
    void aGatewayThatCannotBeReachedIsGatewayError(String url) {
        GatewayDataProviderPlugin plugin = new GatewayDataProviderPlugin(url, TOKEN, 2000, 10000);

        DataProviderExchangeException e = assertThrows(DataProviderExchangeException.class,
                () -> plugin.fetchData(Map.of("sub", "ait-2026-0001", "scope", "ait_transcript_vc_ldp")));
        assertEquals("gateway_error", e.getErrorCode());
    }

    @Test
    void aGatewaySlowerThanTheReadTimeoutIsGatewayError() throws Exception {
        GatewayDataProviderPlugin plugin = plugin(200);
        delayMs = 1000;

        long start = System.nanoTime();
        DataProviderExchangeException e = assertThrows(DataProviderExchangeException.class,
                () -> plugin.fetchData(Map.of("sub", "ait-2026-0001", "scope", "ait_transcript_vc_ldp")));
        assertEquals("gateway_error", e.getErrorCode());
        assertTrue(System.nanoTime() - start < 800_000_000L, "the read timeout did not cut the call short");
    }

    /** Keycloak always puts sub in its tokens, so the stack cannot produce this case; only this test covers it. */
    @Test
    void claimsWithoutSubAreInvalidAccessTokenAndTheGatewayIsNotCalled() throws Exception {
        GatewayDataProviderPlugin plugin = plugin();
        Map<String, Object> blankSub = new HashMap<>(Map.of("sub", "", "scope", "ait_transcript_vc_ldp"));
        Map<String, Object> nullSub = new HashMap<>(Map.of("scope", "ait_transcript_vc_ldp"));
        nullSub.put("sub", null);

        for (Map<String, Object> claims : List.of(Map.<String, Object>of("scope", "ait_transcript_vc_ldp"), blankSub, nullSub)) {
            DataProviderExchangeException e = assertThrows(DataProviderExchangeException.class,
                    () -> plugin.fetchData(claims));
            assertEquals("invalid_access_token", e.getErrorCode(), claims.toString());
        }
        assertEquals(List.of(), seen);
    }

    @Test
    void makesNoCallUntilAskedForData() throws Exception {
        plugin();
        assertEquals(List.of(), seen);
    }
}
