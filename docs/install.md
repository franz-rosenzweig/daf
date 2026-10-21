<sub>[Daf docs](README.md) › Getting started</sub>

# Install

This page covers every way into Daf: the web app, which is the whole thing, and the Mac app, the Android app, the Kindle plugin and the browser extension, which each add something around it. Daf has one sign-in, a username and a password, so all of these connect to one copy of Daf running on a server. My own copy is at https://daf.tiresia.xyz, and if you want one of your own, [Your own server](server.md) explains how it runs.

## On the web

Open your Daf's address in any browser and sign in with the username and password. The sign-in lasts a year on that browser. Five wrong tries from one address lock it for 15 minutes, which means a lost password is annoying but nobody can guess their way in.

To change the password, go to **Preferences → Account**, type the new one and the current one, and press **Save**. A new password signs out every other browser at once. On the server, `daf set-password` does the same thing.

### Install it as an app

On an Android phone, open Daf in Chrome, then the browser menu → **Install app**. Daf gets its own icon and window, and "Save to Daf" shows up in the share menu, so a link or a photo of a marked page goes straight in. On an iPhone, Safari's **Share → Add to Home Screen** gives you the icon and the window.

Offline reading only works on an https address, because browsers only run the offline part (a service worker) on secure addresses. Once Daf has one, every page, article and book you've opened before keeps working with no signal.

## The Mac app

There's no download yet, so you build it from this repository, which takes about ten seconds once the tools are there. You need macOS 13 or newer, the Command Line Tools (`xcode-select --install`) and XcodeGen (`brew install xcodegen`).

```sh
cd mac
./build.sh
cp -R build/Daf.app /Applications/ && open /Applications/Daf.app
```

Sign in inside the window, then open **Daf → Settings…** and press **Connect This Mac**, which gives the menu bar and "Save to Daf" their own token. The details, including signing it so the Keychain stops asking, are in [the Mac app](mac.md) and [mac/README.md](../mac/README.md).

## The Android app

The Android app is built from the repository too, on a computer with JDK 17 and the Android SDK, and it needs a keystore of your own to sign it.

```sh
cd android
./release.sh path/to/keystore.properties
adb install -r Daf-0.2.5.apk
```

The version in the file name follows `versionName` in `android/app/build.gradle`. Sign in inside the app and it connects itself: the widget, the share sheet and the nudge get a token of their own without you doing anything, one for each phone or tablet. See [the Android app](android.md) and [android/README.md](../android/README.md).

## The Kindle plugin

The plugin is for KOReader, so the Kindle needs KOReader first. Then:

1. Copy the folder `kindle/daf.koplugin` into KOReader's `plugins` folder on the Kindle (`koreader/plugins/`).
2. On the server, make a token for it with `daf kindle-token kindle`. It's printed ONCE, so copy it right away.
3. Create `koreader/settings/daf.lua` with your address and the token:

   ```lua
   return {
       ["url"] = "https://your-daf-address",
       ["token"] = "the token from step 2",
       ["sleep_screen"] = true,
   }
   ```

4. Restart KOReader and look under **Tools → Daf**. **Send reading time now** is a good first test.

I install mine with `tools/install-kindle.sh`, which does the same thing over SSH, but it's written for my Kindle. More in [the Kindle](kindle.md).

## The browser extension

- **Firefox or Zen:** in Daf, open **Preferences → Account**, and under "Browser extension" download the file for **Firefox or Zen**. Then `about:addons` → the gear → **Install Add-on From File…**. From version 0.5.1 on, it updates itself after that, like any other add-on.
- **Chrome or Arc:** download the file for **Chrome or Arc** from the same place and unzip it, then open `chrome://extensions`, turn on **Developer mode** and press **Load unpacked**.
- **Safari:** it comes inside the Mac app. Tick **Daf** in Safari → Settings → Extensions and allow it on every website.

For Firefox, Zen, Chrome and Arc, press **Make a token** under "Browser extension", then paste it in the extension's **Options** and press **Save and connect**. [The browser extension](browser-extension.md) has the rest.

## Connected devices

Everything other than a browser window uses a device token instead of your password, and **Preferences → Account → Connected devices** lists them all, with **Disconnect** next to each one. If you ever lose a phone or a laptop, that's the button to press, and its token stops working right away.

If something here doesn't work the way I describe it, tell me, and I'll fix the page or the app.

<sub>Next: [Today and goals](today-and-goals.md) →</sub>
