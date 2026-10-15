-- Point the ait-transcript credential's JSON-LD context at :'new_url'.
-- Run by bootstrap.sh context_refresh():  psql -v new_url=<url> -tA < context_refresh.sql
--
-- The URL lives in two places that must change together: the `context` column
-- (issuer metadata, QR signing lookup) and inside the base64 `vc_template` (what
-- Certify actually signs). Replaces whatever URL is there, so it is idempotent and
-- works in both directions. Prints "1" when a row changed, nothing otherwise.
-- Credentials already issued keep the URL they were signed with.
UPDATE certify.credential_config
SET context = regexp_replace(context, '[^,]*academic-transcript-context\.json', :'new_url'),
    vc_template = translate(encode(convert_to(
        regexp_replace(convert_from(decode(vc_template, 'base64'), 'UTF8'),
                       '"[^"]*academic-transcript-context\.json"', '"' || :'new_url' || '"'),
        'UTF8'), 'base64'), E'\n', ''),  -- encode() wraps at 76 chars; Certify's decoder rejects newlines
    upd_dtimes = NOW()
WHERE credential_config_key_id = 'ait-transcript'
  AND (context IS DISTINCT FROM regexp_replace(context, '[^,]*academic-transcript-context\.json', :'new_url')
       OR convert_from(decode(vc_template, 'base64'), 'UTF8') NOT LIKE '%"' || :'new_url' || '"%')
RETURNING 1;
