<sub>[Daf docs](README.md) › Devices</sub>

# Reader apps

For years my RSS lived in FreshRSS, and I read it in Read You on my phone, which talked to FreshRSS through what's called the "Google Reader API". When Daf started reading the feeds itself, FreshRSS wasn't needed any more, so I retired it. Daf now speaks that same API, which means any app that worked with FreshRSS works with Daf's Feed: Read You, NetNewsWire, Reeder, FocusReader, Fluent Reader, newsboat, and plenty of others.

Basically, instead of the app reading FreshRSS and Daf reading FreshRSS, the app reads Daf, and there's only ONE Feed.

## What the app sees

The app sees the Feed the way Daf counts it. Anything I've marked seen in Daf is read in the app, and anything older than the Feed's window (**Preferences → Reader → The Feed lets go after**) is read too, so the unread count in the app matches the one in Daf's sidebar.

Reading goes both ways, and it's immediate. Open an article in the app, or mark it read there, and it's seen in Daf right away. Mark something seen or unseen in Daf, and the app has it at its next sync. "Mark all as read" in the app marks the feed or folder seen in Daf as well.

A star in the app is the Shortlist. When I star an article in Read You, Daf saves it to the Library and puts it on the Shortlist, which is where I look for what I mean to read soon. Starring it doesn't mark it read, since that's still the app's call. Taking the star off takes it off the Shortlist, but it stays in the Library. It works the other way too: something I put on the Shortlist in Daf shows up starred in the app, as long as its post is still in the Feed. A starred post stays in the Feed for good, so the app's starred list doesn't lose it after a month.

Folders are folders, and they're the same ones Daf has. Following a site from the app follows it in Daf, in the folder I pick, and renaming, moving or unfollowing a feed does the same in Daf. Renaming a folder renames it in Daf, so keep the **Divrei Torah** folder's name as it is, since the Torah page reads that folder.

A few things stay in the app. Tags (some apps call them labels) that you put on single articles aren't kept by Daf, and only the Feed goes to the apps, not the Library, the books or the highlights. Highlighting is still something I do in Daf.

## The API password

The app doesn't sign in with my Daf password. It gets a password of its own, which keeps my real one off my phone's apps, and which I can take back at any time without touching anything else.

In Daf, go to **Preferences → Reader apps** (it's under Connections). The card shows the server's address, the Google Reader API address and my username, each with a **Copy** button. Press **Make a password** and Daf makes one, four groups of five letters and numbers, like `k7m2p-x9rta-4hwnc-q3vze`. Copy it into the app right away, because Daf shows it only ONCE. If I lose it, **New password** makes another one, and **Remove** turns the API off.

Either button signs every app out at once, which is exactly what I want if a phone goes missing: press **New password**, and the old one stops working everywhere. The card also says when the password was made and when an app last used it, which is a quick way to see that an app is really syncing.

Five wrong passwords from one place lock that place out for 15 minutes, and twenty from anywhere in an hour pause the API's sign-in for 15 minutes and send me a message. My Daf sign-in isn't affected either way, so an app with an old password can't lock me out of Daf itself.

## Setting up an app

Every app asks for the same three things: an address, a username and a password. The username is my Daf username (the one in **Preferences → Account**), and the password is the API password from above, never my Daf password.

For the address, use the Google Reader API address from the card, `https://daf.tiresia.xyz/api/greader.php`. It works whether an app asks for a "FreshRSS" server or a "Google Reader" one, because Daf forgives an app that adds `/api/greader.php` to it a second time. The apps that add it themselves also take just `https://daf.tiresia.xyz`.

**Read You** (Android). Add an account and pick **FreshRSS**. Put the API address in "Server address", then the username and the API password, and let it sync. If your Read You has a "Google Reader" account type, that one takes the same address too.

**NetNewsWire** (Mac and iPhone). In Settings, add an account and pick **FreshRSS**. It asks for an "API URL", which is the API address, then the username and the API password.

**newsboat** (the terminal). Put these lines in its config file, with your own username and API password:

```
urls-source "freshrss"
freshrss-url "https://daf.tiresia.xyz/api/greader.php"
freshrss-login "your-username"
freshrss-password "the-api-password"
freshrss-flag-star "s"
```

newsboat needs the whole API address here: given just the server, it can't sign in. The last line makes the "s" flag the star, so flagging an article with Ctrl-E and "s" puts it on the Shortlist. Opening an article marks it read in Daf, and **A** on a feed marks the whole feed read.

If an app says it can't sign in, check that the password is the API password and not the Daf one, and that it's the newest one. If I've pressed **New password** since, the app needs the new one too.

<sub>Next: [Your own server](server.md) →</sub>
