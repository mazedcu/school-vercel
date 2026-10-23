# Radon Academy — Android app

An Android app that opens **https://opdevsystems.xyz** full screen, so staff,
students and parents can use the coaching management system like a normal app.

## What it does

- Opens the website and keeps people logged in between launches.
- **Print or save as PDF** buttons (report cards, CT reports) open Android's
  print screen, where you can print or save a PDF.
- PDF downloads (timetables, ID cards, lesson plans) save to **Downloads**
  and keep the login, so protected files download properly.
- Photo and file uploads from forms work.
- The back button goes to the previous page; on the first page it leaves the app.
- Pull down to refresh, a thin loading bar, and a "Try again" screen when offline.
- Phone numbers, email, WhatsApp and other websites open in their own apps.
- Links to opdevsystems.xyz shared on WhatsApp etc. can open in the app.
- Only secure (https) connections are allowed.

## Build the APK

1. Install **Android Studio** (Narwhal 2025.1 or newer) from developer.android.com/studio.
2. Unzip this folder and choose **File → Open**, then select the `RadonAcademyApp` folder.
3. Wait for "Gradle sync" to finish. The first time, it downloads the Android tools (a few minutes).
4. **Build → Build App Bundle(s) / APK(s) → Build APK(s)**.
5. Click **locate** in the message that appears. The file is
   `app/build/outputs/apk/debug/app-debug.apk`. Send it to a phone and open it
   to install (allow "install unknown apps" when asked).

To try it straight away, plug in an Android phone with USB debugging on and press ▶ Run.

## Release version (to share widely or publish on Google Play)

1. **Build → Generate Signed App Bundle or APK**.
2. Choose **Android App Bundle** for Google Play, or **APK** to share the file directly.
3. Create a new key store when asked, and **keep the .jks file and its passwords
   safe**. Every future update must be signed with the same key.
4. Choose the **release** build.

For Google Play you'll also need the 512×512 icon included here
(`play-store-icon-512.png`), a few screenshots, a short description and a
privacy policy page.

## Updating the app

- **Website changes need no app update.** The app always shows the live site.
- To change the website address, edit `START_URL` and `SITE_HOST` in
  `app/build.gradle.kts`, and the two `android:host` lines in
  `app/src/main/AndroidManifest.xml`.
- For each new version you publish, increase `versionCode` (and usually
  `versionName`) in `app/build.gradle.kts`.

## The website must use HTTPS

The app refuses plain `http://` connections, so passwords and marks are always
encrypted. Check by opening https://opdevsystems.xyz in Chrome on a phone; you
should see the padlock. If not, run this on the server (DigitalOcean console):

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d opdevsystems.xyz -d www.opdevsystems.xyz
```

The domain's DNS must point to the server, and the nginx `server_name` line must
list `opdevsystems.xyz www.opdevsystems.xyz`. The Django settings already trust
HTTPS behind nginx (`SECURE_PROXY_SSL_HEADER` and `CSRF_TRUSTED_ORIGINS`).

## Technical details

- Kotlin, single activity (`MainActivity.kt`), Android 7.0 (API 24) and newer,
  targets API 36.
- Android Gradle Plugin 8.11.1, Gradle 8.14.3, Kotlin 2.0.21, JDK 17.
- Package name: `com.radonacademy.app`.
- The website can detect the app: its user agent ends in `RadonAcademyApp/<version>`.
