# Inji Wallet for the AIT transcript platform

The changes that make **Inji Wallet v0.22.1** talk to the AIT transcript platform on GCP, as patches on top of the upstream release. This repo does not carry Inji Wallet itself: `apply.sh` clones [inji/inji-wallet](https://github.com/inji/inji-wallet) at `v0.22.1` (MIT, MOSIP) and applies them.

```
wallet/
  apply.sh            ./wallet/apply.sh <platform> [dest-dir]
  common/             changes both platforms need
  ios/                iOS signing, Xcode 27 / iOS 27 fixes (see ios/README.md)
```

| Platform | Status | Use |
|---|---|---|
| **iOS** | verified on a physical iPhone via TestFlight | `BUNDLE_ID=com.yourorg.aitwallet TEAM_ID=ABCDE12345 ./wallet/apply.sh ios my-wallet`; then follow [ios/README.md](./ios/README.md) |
| **Android** | **untried**, no patch yet | `common/` applies, but you set your own application id and signing; see below |

## `common/`

One file, `.env`: `MIMOTO_HOST`, `ESIGNET_HOST` and `OBSRV_HOST` point at `https://api.transcript-demo.ait-vc.dpi.ait.ac.th`. It is plain JavaScript config read by both platforms. Pointing `OBSRV_HOST` at the platform also stops usage telemetry going to MOSIP. Connection details and the flow: [wiki/guides/wallet-developer-urls.md](../wiki/guides/wallet-developer-urls.md).

## Android

Nothing Android-specific has been built or run here, so there is no `android/` folder yet. What is known from the Inji Wallet source:

- The app registers the `io.mosip.residentapp.inji` URL scheme the login redirects to, so no change is expected there.
- It has its own application ids per flavor (`io.mosip.inji.wallet` for the main one) and no signing config for you: set your own.
- Toolchain per the upstream README: Java 17, Gradle 8.6, Android SDK 35.
- On the platform side, Android's OpenID4VCI library does not enforce the issuer check that broke iOS, and the public VC context URL matters more there (its verifier loads contexts over the network).

To add Android: apply `common/ait-common.patch` to a `v0.22.1` checkout, make it build and complete a download, then put what you needed in `android/ait-android.patch` plus an `android/README.md`, and add the platform to `apply.sh`. Do not add the folder before it has been run.

## Maintaining the patches

Each patch is a staged diff of that platform's files against the upstream tag, with the signing identity written as the placeholders `com.example.aitwallet` and `XXXXXXXXXX`:

```sh
git add -A && git diff --cached --binary v0.22.1 -- <that platform's paths> > <this repo>/wallet/<platform>/ait-<platform>.patch
```

Leave out your own build number and any allow-list for your secret-scan hook. Verify by running `apply.sh` into a new directory with your `BUNDLE_ID` / `TEAM_ID` and checking that it builds and matches your checkout apart from those values. Newer Inji Wallet releases may already contain some of the iOS workarounds.
