package asia.mosip.issuer.gateway.plugin;

import io.mosip.certify.api.exception.DataProviderExchangeException;
import io.mosip.certify.api.spi.DataProviderPlugin;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Certify's data provider for the Issuer: posts the access-token claims to the Gateway's {@code POST /issuances}
 * (contracts.md section 2a) and hands the claim set back to Certify. It knows one URL, one secret and two timeouts,
 * and no claim names. It makes no call until Certify asks for data, so Certify starts whether or not the Gateway is up.
 */
@Component
@ConditionalOnProperty(value = "mosip.certify.integration.data-provider-plugin", havingValue = "GatewayDataProviderPlugin")
public class GatewayDataProviderPlugin implements DataProviderPlugin {

    private static final Logger log = LoggerFactory.getLogger(GatewayDataProviderPlugin.class);
    private static final String GATEWAY_ERROR = "gateway_error";

    private final URI issuances;
    private final String authorization;
    private final Duration readTimeout;
    private final HttpClient http;

    public GatewayDataProviderPlugin(
            @Value("${mosip.certify.gateway.url}") String url,
            @Value("${mosip.certify.gateway.auth-token}") String authToken,
            @Value("${mosip.certify.gateway.connect-timeout-ms:2000}") long connectTimeoutMs,
            @Value("${mosip.certify.gateway.read-timeout-ms:10000}") long readTimeoutMs) {
        this.issuances = URI.create(url.replaceAll("/+$", "") + "/issuances");
        this.authorization = "Bearer " + authToken;
        this.readTimeout = Duration.ofMillis(readTimeoutMs);
        this.http = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofMillis(connectTimeoutMs))
                .build();
        log.info("GatewayDataProviderPlugin selected: credential requests go to {}", issuances);
    }

    /**
     * The Gateway's claim set for the token, with every top-level object or array turned into its JSON text, since
     * Certify's Velocity template substitutes text (the template's unquoted {@code ${courses}}).
     *
     * @throws DataProviderExchangeException {@code invalid_access_token} for claims without {@code sub}, before any
     *     call; the refusal body's {@code error} for any non-2xx answer; {@code gateway_error} when there is no such
     *     body, or the Gateway cannot be reached or does not answer within the read timeout
     */
    @Override
    public JSONObject fetchData(Map<String, Object> claims) throws DataProviderExchangeException {
        if (!(claims.get("sub") instanceof String sub) || sub.isEmpty()) {
            throw new DataProviderExchangeException("invalid_access_token");
        }
        Map<String, Object> body = new HashMap<>(claims);
        body.remove("accessTokenHash");
        HttpRequest request = HttpRequest.newBuilder(issuances)
                .timeout(readTimeout)
                .header("Authorization", authorization)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(new JSONObject(body).toString()))
                .build();
        HttpResponse<String> response;
        try {
            response = http.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (IOException e) {
            log.warn("Gateway not reached at {}: {}", issuances, e.toString());
            throw new DataProviderExchangeException(GATEWAY_ERROR);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new DataProviderExchangeException(GATEWAY_ERROR);
        }
        if (response.statusCode() / 100 != 2) {
            throw new DataProviderExchangeException(errorCode(response.body()));
        }
        JSONObject result;
        try {
            result = new JSONObject(response.body());
        } catch (JSONException e) {
            throw new DataProviderExchangeException(GATEWAY_ERROR);
        }
        for (String key : result.keySet()) {
            Object value = result.get(key);
            if (value instanceof JSONObject || value instanceof JSONArray) {
                result.put(key, value.toString());
            }
        }
        return result;
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
