-- The hackathon installation's credential_config rows, seeded on a fresh database only.
-- vc-stack/issuer/compose.yaml mounts this file as /docker-entrypoint-initdb.d/certify_seed.sql,
-- a name that sorts after vc-stack/certify_init.sql, which creates the table.
\c inji_certify postgres

-- Developer Passport: VCDM 2.0, claims straight from the roster (the Gateway's on_roster check gates it).
-- Display metadata as in ait-vc's DeveloperPassportCredential row, minus the dropped vpid and anchorId.
-- did_url placeholder — bootstrap.sh did_refresh overwrites.
INSERT INTO certify.credential_config (
    credential_config_key_id, config_id, status, vc_template, doctype, sd_jwt_vct, context,
    credential_type, credential_format, did_url, key_manager_app_id, key_manager_ref_id,
    signature_algo, signature_crypto_suite, sd_claim, display, display_order, scope,
    cryptographic_binding_methods_supported, credential_signing_alg_values_supported,
    proof_types_supported, credential_subject, mso_mdoc_claims, plugin_configurations,
    credential_status_purpose, qr_settings, qr_signature_algo, cr_dtimes, upd_dtimes
) VALUES (
    'developer-passport', gen_random_uuid()::VARCHAR(255), 'active', 'ewogICJAY29udGV4dCI6IFsKICAgICJodHRwczovL3d3dy53My5vcmcvbnMvY3JlZGVudGlhbHMvdjIiLAogICAgImh0dHA6Ly9ob3N0LmRvY2tlci5pbnRlcm5hbDo5MDk4L2NvbnRleHRzL2RldmVsb3Blci1wYXNzcG9ydC92MS5qc29uIiwKICAgICJodHRwczovL3czaWQub3JnL3NlY3VyaXR5L3N1aXRlcy9lZDI1NTE5LTIwMjAvdjEiCiAgXSwKICAiaXNzdWVyIjogIiR7X2lzc3Vlcn0iLAogICJ0eXBlIjogWwogICAgIlZlcmlmaWFibGVDcmVkZW50aWFsIiwKICAgICJEZXZlbG9wZXJQYXNzcG9ydENyZWRlbnRpYWwiCiAgXSwKICAidmFsaWRGcm9tIjogIiR7dmFsaWRGcm9tfSIsCiAgInZhbGlkVW50aWwiOiAiJHt2YWxpZFVudGlsfSIsCiAgImNyZWRlbnRpYWxTdGF0dXMiOiB7CiAgICAiaWQiOiAiJHtjcmVkZW50aWFsU3RhdHVzLmlkfSIsCiAgICAidHlwZSI6ICIke2NyZWRlbnRpYWxTdGF0dXMudHlwZX0iLAogICAgInN0YXR1c1B1cnBvc2UiOiAiJHtjcmVkZW50aWFsU3RhdHVzLnN0YXR1c1B1cnBvc2V9IiwKICAgICJzdGF0dXNMaXN0SW5kZXgiOiAiJHtjcmVkZW50aWFsU3RhdHVzLnN0YXR1c0xpc3RJbmRleH0iLAogICAgInN0YXR1c0xpc3RDcmVkZW50aWFsIjogIiR7Y3JlZGVudGlhbFN0YXR1cy5zdGF0dXNMaXN0Q3JlZGVudGlhbH0iCiAgfSwKICAiY3JlZGVudGlhbFN1YmplY3QiOiB7CiAgICAiaWQiOiAiJHtfaG9sZGVySWR9IiwKICAgICJ0ZWFtSWQiOiAiJHt0ZWFtSWR9IiwKICAgICJ0ZWFtTmFtZSI6ICIke3RlYW1OYW1lfSIsCiAgICAib2lkY0NsaWVudElkIjogIiR7b2lkY0NsaWVudElkfSIsCiAgICAiYXV0aEVuZHBvaW50IjogIiR7YXV0aEVuZHBvaW50fSIsCiAgICAiaXNzdWVyRW5kcG9pbnQiOiAiJHtpc3N1ZXJFbmRwb2ludH0iLAogICAgInZlcmlmaWVyRW5kcG9pbnQiOiAiJHt2ZXJpZmllckVuZHBvaW50fSIKICB9Cn0=', NULL, NULL,
    'http://host.docker.internal:9098/contexts/developer-passport/v1.json,https://www.w3.org/ns/credentials/v2',
    'DeveloperPassportCredential,VerifiableCredential', 'ldp_vc',
    'did:key:z6MkpPLACEHOLDERreplaceMeViaBootstrapDidRefreshScript1',
    'CERTIFY_VC_SIGN_ED25519', 'ED25519_SIGN', 'EdDSA', 'Ed25519Signature2020', NULL,
    '[{"name": "AIT Developer Passport", "locale": "en", "logo": {"url": "https://ait.ac.th/wp-content/uploads/2024/09/AIT_globe.png", "alt_text": "AIT Logo"}, "background_color": "#0f766e", "text_color": "#FFFFFF", "background_image": {"uri": "https://ait.ac.th/wp-content/uploads/2024/09/AIT_globe.png"}}]'::JSONB,
    ARRAY['teamName', 'teamId', 'oidcClientId', 'authEndpoint', 'issuerEndpoint', 'verifierEndpoint']::TEXT[],
    'developer_passport_vc_ldp', ARRAY['did:jwk'], ARRAY['Ed25519Signature2020'],
    '{"jwt": {"proof_signing_alg_values_supported": ["RS256", "ES256"]}}'::JSONB,
    '{"teamId": {"display": [{"name": "Team ID", "locale": "en"}]}, "teamName": {"display": [{"name": "Team", "locale": "en"}]}, "oidcClientId": {"display": [{"name": "OIDC Client ID", "locale": "en"}]}, "authEndpoint": {"display": [{"name": "Sign-in Endpoint", "locale": "en"}]}, "issuerEndpoint": {"display": [{"name": "Issuer Endpoint", "locale": "en"}]}, "verifierEndpoint": {"display": [{"name": "Verifier Endpoint", "locale": "en"}]}}'::JSONB,
    NULL, NULL, ARRAY['revocation'],
    '[{"Team": "${teamName}"}]'::JSONB, 'EdDSA', NOW(), NULL
);

-- Achievement Certificate: VCDM 2.0, claims straight from the roster (the Gateway's on_roster and winner checks gate it).
-- Display metadata as in ait-vc's AchievementCertificateCredential row, minus the dropped vpid and anchorId.
INSERT INTO certify.credential_config (
    credential_config_key_id, config_id, status, vc_template, doctype, sd_jwt_vct, context,
    credential_type, credential_format, did_url, key_manager_app_id, key_manager_ref_id,
    signature_algo, signature_crypto_suite, sd_claim, display, display_order, scope,
    cryptographic_binding_methods_supported, credential_signing_alg_values_supported,
    proof_types_supported, credential_subject, mso_mdoc_claims, plugin_configurations,
    credential_status_purpose, qr_settings, qr_signature_algo, cr_dtimes, upd_dtimes
) VALUES (
    'achievement-certificate', gen_random_uuid()::VARCHAR(255), 'active', 'ewogICJAY29udGV4dCI6IFsKICAgICJodHRwczovL3d3dy53My5vcmcvbnMvY3JlZGVudGlhbHMvdjIiLAogICAgImh0dHA6Ly9ob3N0LmRvY2tlci5pbnRlcm5hbDo5MDk4L2NvbnRleHRzL2FjaGlldmVtZW50L3YxLmpzb24iLAogICAgImh0dHBzOi8vdzNpZC5vcmcvc2VjdXJpdHkvc3VpdGVzL2VkMjU1MTktMjAyMC92MSIKICBdLAogICJpc3N1ZXIiOiAiJHtfaXNzdWVyfSIsCiAgInR5cGUiOiBbCiAgICAiVmVyaWZpYWJsZUNyZWRlbnRpYWwiLAogICAgIkFjaGlldmVtZW50Q2VydGlmaWNhdGVDcmVkZW50aWFsIgogIF0sCiAgInZhbGlkRnJvbSI6ICIke3ZhbGlkRnJvbX0iLAogICJ2YWxpZFVudGlsIjogIiR7dmFsaWRVbnRpbH0iLAogICJjcmVkZW50aWFsU3RhdHVzIjogewogICAgImlkIjogIiR7Y3JlZGVudGlhbFN0YXR1cy5pZH0iLAogICAgInR5cGUiOiAiJHtjcmVkZW50aWFsU3RhdHVzLnR5cGV9IiwKICAgICJzdGF0dXNQdXJwb3NlIjogIiR7Y3JlZGVudGlhbFN0YXR1cy5zdGF0dXNQdXJwb3NlfSIsCiAgICAic3RhdHVzTGlzdEluZGV4IjogIiR7Y3JlZGVudGlhbFN0YXR1cy5zdGF0dXNMaXN0SW5kZXh9IiwKICAgICJzdGF0dXNMaXN0Q3JlZGVudGlhbCI6ICIke2NyZWRlbnRpYWxTdGF0dXMuc3RhdHVzTGlzdENyZWRlbnRpYWx9IgogIH0sCiAgImNyZWRlbnRpYWxTdWJqZWN0IjogewogICAgImlkIjogIiR7X2hvbGRlcklkfSIsCiAgICAidGVhbUlkIjogIiR7dGVhbUlkfSIsCiAgICAiYXdhcmQiOiAiJHthd2FyZH0iCiAgfQp9', NULL, NULL,
    'http://host.docker.internal:9098/contexts/achievement/v1.json,https://www.w3.org/ns/credentials/v2',
    'AchievementCertificateCredential,VerifiableCredential', 'ldp_vc',
    'did:key:z6MkpPLACEHOLDERreplaceMeViaBootstrapDidRefreshScript1',
    'CERTIFY_VC_SIGN_ED25519', 'ED25519_SIGN', 'EdDSA', 'Ed25519Signature2020', NULL,
    '[{"name": "AIT Achievement Certificate", "locale": "en", "logo": {"url": "https://ait.ac.th/wp-content/uploads/2024/09/AIT_globe.png", "alt_text": "AIT Logo"}, "background_color": "#7c3aed", "text_color": "#FFFFFF", "background_image": {"uri": "https://ait.ac.th/wp-content/uploads/2024/09/AIT_globe.png"}}]'::JSONB,
    ARRAY['award', 'teamId']::TEXT[],
    'achievement_certificate_vc_ldp', ARRAY['did:jwk'], ARRAY['Ed25519Signature2020'],
    '{"jwt": {"proof_signing_alg_values_supported": ["RS256", "ES256"]}}'::JSONB,
    '{"teamId": {"display": [{"name": "Team ID", "locale": "en"}]}, "award": {"display": [{"name": "Award", "locale": "en"}]}}'::JSONB,
    NULL, NULL, ARRAY['revocation'],
    '[{"Award": "${award}"}]'::JSONB, 'EdDSA', NOW(), NULL
);
