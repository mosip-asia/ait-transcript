---
title: Wallet developer URLs
description: The endpoints and settings a developer needs to point their own wallet (built on Inji Wallet) at the AIT transcript demo on GCP.
tags:
  - guide
  - mobile
  - developers
---
# Wallet developer URLs

For people building their own wallet, based on [inji/inji-wallet](https://github.com/inji/inji-wallet) v0.22.1, against the public demo. How the stack serves a phone and why is in [reference/inji-mobile-wallet.md](../reference/inji-mobile-wallet.md).

## The one setting that matters

| Setting (`.env`) | Value |
|---|---|
| `MIMOTO_HOST` | `https://api.transcript-demo.ait-vc.dpi.ait.ac.th` |

No trailing slash and **no `/v1/mimoto`**: the app appends `/v1/mimoto/...` itself, and a path in the host gives `/v1/mimoto/v1/mimoto/issuers`. It is read at build time (`react-native-dotenv` caches it, so clear Metro's cache after changing it). `ESIGNET_HOST` and `OBSRV_HOST` are not used by this flow; point them at the same host so the app does not call MOSIP's servers. Keep `CREDENTIAL_REGISTRY_EDIT=true` in dev builds if you want to change the Mimoto host from the in-app Settings screen.

## Endpoints

| Hostname | Role | What a wallet calls |
|---|---|---|
| `api.transcript-demo.ait-vc.dpi.ait.ac.th` | Mimoto + Certify gateway | `/v1/mimoto/issuers`, `/v1/mimoto/allProperties`, `/v1/mimoto/verifiers`, `POST /v1/mimoto/get-token/AITUniversity`, `/.well-known/openid-credential-issuer`, `POST /v1/certify/issuance/credential` |
| `keycloak.transcript-demo.ait-vc.dpi.ait.ac.th` | Login (realm `inji`) | `/realms/inji/protocol/openid-connect/auth` in a WebView; `/realms/inji/.well-known/oauth-authorization-server` for discovery |
| `verify.transcript-demo.ait-vc.dpi.ait.ac.th` | Inji Verify (browser) | Scan or upload a credential QR here to check it |
| `wallet.transcript-demo.ait-vc.dpi.ait.ac.th` | Inji Web (browser wallet) | Not needed by a mobile wallet; useful to compare behaviour |

Nothing else is exposed or needed. Do not use the Docker names that may appear in some responses (`keycloak:8080`, `certify-nginx`, `host.docker.internal`): they are for Mimoto inside the stack.

## Issuer and credential

| | |
|---|---|
| Issuer id | `AITUniversity` |
| Credential configuration id | `ait-transcript` |
| Scope | `ait_transcript_vc_ldp` |
| Format | `ldp_vc`, proof `Ed25519Signature2020`, issuer DID `did:key` |
| OAuth client | `wallet-demo` (confidential; Mimoto holds the key) |
| Redirect URI | `io.mosip.residentapp.inji://oauthredirect` (register this URL scheme in your app) |
| Key binding | `did:jwk`; proof JWT `RS256` or `ES256` |

## Flow the wallet follows

1. `GET /v1/mimoto/issuers` on `api.` returns `AITUniversity` with a public `credential_issuer_host`, the redirect URI above and a public `token_endpoint`.
2. Fetch `<credential_issuer_host>/.well-known/openid-credential-issuer`. `authorization_servers` is the public Keycloak.
3. Discover the login URL from `<authorization_server>/.well-known/oauth-authorization-server` (`authorization_endpoint`).
4. Open it in a WebView (PKCE S256, `client_id=wallet-demo`, `scope=ait_transcript_vc_ldp`). The student logs in; Keycloak redirects to the custom scheme with a `code`.
5. **Do not post the code to Keycloak's `token_endpoint`.** Keycloak's own discovery advertises `http://<host>:8080/...` for it, which is not reachable. POST the code (form: `grant_type`, `code`, `client_id`, `redirect_uri`, `code_verifier`) to the issuer list's `token_endpoint`, Mimoto's `get-token/AITUniversity`, which authenticates to Keycloak for the wallet. Inji Wallet already does this for trusted issuers.
6. Build the proof JWT and `POST` to `credential_endpoint` with the bearer token.

## Things that will surprise you

- Mimoto serves two different issuer lists. `api.` `/v1/mimoto/issuers` and `/.well-known/openid-credential-issuer` are the **phone views**; the same paths through `wallet.` return the Docker-internal values Inji Web needs. Always use the `api.` host.
- Mimoto and the app both cache issuer metadata. After the issuer config changes, restart the app (or clear its cache); a stale cache can send a credential request whose `@context` Certify no longer matches.
- Credentials issued before 2026-10-15 carry a `host.docker.internal` JSON-LD context, which an app cannot load when it verifies a credential after download. Reissue them.
- Presenting a credential from the app to Inji Verify (OpenID4VP) is not enabled; verify by QR in the browser.
- The VM runs Mon-Fri 08:30-18:30 Asia/Bangkok only.

## Building the wallet (iOS, Inji Wallet v0.22.1)

Verified end to end on a physical iPhone through TestFlight. **Android has not been tried.**

**Shortcut:** steps 1 to 5 below are packaged as a patch. `BUNDLE_ID=com.yourorg.aitwallet TEAM_ID=ABCDE12345 ./wallet/apply.sh ios my-wallet` (both required; see [wallet/README.md](../../wallet/README.md)) clones v0.22.1 and applies them; continue at step 6. The steps remain here so you can see, and adapt, what changed.

**Prerequisites:** macOS with Xcode 27, Node **20** (RN 0.74 does not take Node 26), CocoaPods >= 1.12 (`brew install cocoapods node@20`; put `/opt/homebrew/opt/node@20/bin` first on `PATH` and set `LANG=en_US.UTF-8`), and an Apple Developer account for a device build or TestFlight. v0.22.1 does **not** run in the iOS Simulator (its MLKit/MLImage pods have no usable arm64 simulator slice), so use a real iPhone.

1. `git clone --branch v0.22.1 https://github.com/inji/inji-wallet.git`
2. **`.env`**: set `MIMOTO_HOST`, `ESIGNET_HOST` and `OBSRV_HOST` to `https://api.transcript-demo.ait-vc.dpi.ait.ac.th` (see above). The Metro cache keeps old values: clear it after changing them.
3. **Signing** (`ios/Inji.xcodeproj`, Debug and Release): your own `PRODUCT_BUNDLE_IDENTIFIER` and `DEVELOPMENT_TEAM`, `CODE_SIGN_STYLE = Automatic`, `CODE_SIGN_IDENTITY = "Apple Development"` (Xcode re-signs for the App Store at export). Point `CODE_SIGN_ENTITLEMENTS` at an empty `<dict/>` plist: the upstream file needs iCloud, Push and Sign in with Apple on your App ID, none of which this flow uses. Keep the `io.mosip.residentapp.inji` URL scheme in `Info.plist`.
4. **Xcode 27 build fixes:**
   - Raise the deployment target to **15.0**: `IPHONEOS_DEPLOYMENT_TARGET` in the project and in the Podfile (`platform :ios, ... '15.0'` and the `post_install` line that forced `14.0`). Xcode 27 rejects anything lower.
   - In the Podfile `post_install` loop that sets build settings, add `SWIFT_ENABLE_EXPLICIT_MODULES = 'NO'` and `CLANG_ENABLE_EXPLICIT_MODULES = 'NO'` (the legacy C crypto pods fail to build otherwise).
   - `node_modules/expo-localization/ios/LocalizationModule.swift`: add `@unknown default: return "unknown"` to the `getUnicodeCalendarIdentifier` switch, then `npx patch-package expo-localization` so the patch survives `npm install`.
5. **iOS 27 scene lifecycle** (without this the app is killed at launch: `___UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption`). Add to `Info.plist`:

   ```xml
   <key>UIApplicationSceneManifest</key>
   <dict>
     <key>UIApplicationSupportsMultipleScenes</key><false/>
     <key>UISceneConfigurations</key>
     <dict>
       <key>UIWindowSceneSessionRoleApplication</key>
       <array><dict>
         <key>UISceneConfigurationName</key><string>Default Configuration</string>
         <key>UISceneDelegateClassName</key><string>SceneDelegate</string>
       </dict></array>
     </dict>
   </dict>
   ```

   and add `ios/Inji/SceneDelegate.h` / `.mm` to the Inji target (RN 0.74 still creates the window in `AppDelegate`, so the scene only adopts it and forwards URLs):

   ```objc
   // SceneDelegate.h
   #import <UIKit/UIKit.h>
   @interface SceneDelegate : UIResponder <UIWindowSceneDelegate>
   @property (strong, nonatomic) UIWindow *window;
   @end

   // SceneDelegate.mm
   #import "SceneDelegate.h"
   #import "AppDelegate.h"
   @implementation SceneDelegate
   - (AppDelegate *)appDelegate { return (AppDelegate *)UIApplication.sharedApplication.delegate; }
   - (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions {
     if (![scene isKindOfClass:[UIWindowScene class]]) return;
     UIWindow *window = [self appDelegate].window;   // created by RCTAppDelegate
     window.windowScene = (UIWindowScene *)scene;
     self.window = window;
     [window makeKeyAndVisible];
     for (UIOpenURLContext *c in connectionOptions.URLContexts)
       [[self appDelegate] application:UIApplication.sharedApplication openURL:c.URL options:@{}];
     for (NSUserActivity *a in connectionOptions.userActivities)
       [[self appDelegate] application:UIApplication.sharedApplication continueUserActivity:a restorationHandler:^(NSArray<id<UIUserActivityRestoring>> *_Nullable r) {}];
   }
   - (void)scene:(UIScene *)scene openURLContexts:(NSSet<UIOpenURLContext *> *)URLContexts {
     for (UIOpenURLContext *c in URLContexts)
       [[self appDelegate] application:UIApplication.sharedApplication openURL:c.URL options:@{}];
   }
   - (void)scene:(UIScene *)scene continueUserActivity:(NSUserActivity *)a {
     [[self appDelegate] application:UIApplication.sharedApplication continueUserActivity:a restorationHandler:^(NSArray<id<UIUserActivityRestoring>> *_Nullable r) {}];
   }
   @end
   ```

   Links that cold-start the app now arrive on the scene; this forwards them, but a cold-start deep link is untested.
6. `npm install`, then `cd ios && pod install` (the TensorFlow pod is a large git clone; rerun if the network resets it), then build or archive with `-allowProvisioningUpdates`. The repo's Talisman pre-commit hook flags `Podfile.lock`, `project.pbxproj` and `Info.plist` as secrets (hex ids); copy the checksums it prints into `.talismanrc`.
7. **TestFlight:** create the App Store Connect record for your bundle id (the App ID must already exist: an archive plus `xcodebuild -exportArchive` with `method = app-store-connect` and `signingStyle = automatic` registers it), then export with `destination = upload`. Each upload needs a higher `CFBundleVersion`.

### Where a failed download stopped

If the app only says the download failed, the request order on the platform tells you which step broke (maintainers can read it in Dozzle): `allProperties` -> `issuers` -> `/.well-known/openid-credential-issuer` -> Keycloak `/.well-known/oauth-authorization-server` -> the login page (`openid-connect/auth`) -> `POST get-token/AITUniversity` -> `POST issuance/credential`. Stopping after the discovery document means the library rejected it (the iOS one checks that `issuer` equals the URL it fetched). Stopping before it means the host, a stale cache or the metadata.

## Test students

Mock students are defined in [data/students.json](../../data/students.json). Ask the demo owner for the shared test password rather than copying one into a wallet repo.

## Quick check

```sh
A=https://api.transcript-demo.ait-vc.dpi.ait.ac.th
curl -s $A/v1/mimoto/issuers | jq '.response.issuers[0] | {credential_issuer_host, redirect_uri, token_endpoint}'
curl -s $A/.well-known/openid-credential-issuer | jq '{credential_issuer, authorization_servers, credential_endpoint}'
curl -s https://keycloak.transcript-demo.ait-vc.dpi.ait.ac.th/realms/inji/.well-known/oauth-authorization-server | jq .authorization_endpoint
```
