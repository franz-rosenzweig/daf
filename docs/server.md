<sub>[Daf docs](README.md) › Running your own server</sub>

# Your own server

This page is about running a copy of Daf yourself: what it needs, where it keeps its state, how to run it as a service, and the `daf` command line. I want to be honest up front: I built Daf for one server, mine, and for the services I already run there, so a copy of your own means pointing it at yours, and in a few places that means editing a path in the code. The full operating notes for my own server, with every detail, are in [How Daf runs](OPERATIONS.md).

## What it is

Daf is one Python process. It serves the web app and the API, pulls every source every five minutes, and works through a queue of slower jobs (reading the pages you save, tags, transcripts, clips, PDFs) in the background. Its data is one SQLite file. The web app is plain JavaScript and CSS served by the same process, so there's no build step: change a file in `web/` and reload the page.

Every source is optional. If one isn't there, it shows up red on the **Sources** page and in `daf doctor`, and the others carry on.

## Setting it up

You need Python 3.12. From a clone of the repository:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
export DAF_STATE=~/daf-state DAF_VAULT=~/vault DAF_HOSTS=127.0.0.1
bin/daf set-password --user yourname
.venv/bin/python -m daf.server
```

`set-password` asks for the password twice (or makes one with `--random` and leaves it in the state folder), and the username is what you'll type on the sign-in page. The last line starts Daf by hand, so you can open http://127.0.0.1:8440 and see that it works before making it a service.

## Settings that come from the environment

| Variable | What it is | Mine |
|---|---|---|
| `DAF_STATE` | the state folder (below) | `/srv/docker/daf` |
| `DAF_VAULT` | the Obsidian vault Daf writes into | my vault |
| `DAF_HOSTS`, `DAF_PORT` | the addresses and port to listen on | localhost and my tailnet address, 8440 |
| `DAF_FRESHRSS_URL` | FreshRSS, for the Feed | `http://127.0.0.1:8080` |
| `DAF_CWA_INGEST` | Calibre-Web-Automated's import folder, for books you add | `/srv/docker/cwa-ingest` |
| `DAF_KINDLE_DIR` | where Send to Kindle writes, synced to the Kindle | a `Daf` folder in the Kindle's books |
| `DAF_KOMGA_CONF`, `DAF_MANGA_ROOT` | Komga's address and keys, and the manga folder | my manga setup |

Passwords and keys go in a file called `daf.env` in the state folder, one `NAME=value` per line: `DAF_FRESHRSS_USER` and `DAF_FRESHRSS_PASS` (FreshRSS's API password), `DAF_KARAKEEP_KEY`, `HARDCOVER_API_KEY`, and `DAF_CLAUDE_MODEL` if you want a different model (**Preferences → AI** can pick one too).

The rest is set at the top of `daf/config.py`: where to find KoInsight's database, Audiobookshelf's database and user, the Calibre libraries, and Karakeep. A few tools are set where they're used: the Claude command-line tool (in `ai.py` and `paper_pages.py`), yt-dlp (`media.py`), the Kokoro read-aloud server, which Daf finds as a Docker container named `kokoro-tts`, and the headless Chrome that reads pages a plain download can't, a Docker container named `docker-chrome-1` (`browser.py`). The newsletters and the morning email go through Proton Mail Bridge (`sources/newsletters.py` and `digest.py`), and **Send feedback** files its issue with the GitHub command-line tool, `gh` (`feedback.py`).

## The state folder

Everything Daf knows that isn't in a source or the vault lives in one folder:

- `daf.db`, the database. Most of it is an index that `daf sync` rebuilds from the sources and the vault, but it also holds Daf's own things, like the Library, the review schedule, flashcards, shelves, places in books, device tokens and Kindle page turns that never reached KoInsight, so back it up like any database.
- `auth.json`, the password hash and the secret that signs the cookies. Changing the password replaces the secret, which signs out every browser.
- `settings.json`, the preferences you set in the app, plus a few things you set by hand: `private_titles`, the words that make a book private, `public_url`, the https address that links in messages point to, `library.karakeep`, whether Karakeep still keeps the Library (`on`, the old way), is only read (`read`, which `daf karakeep-import` sets) or isn't asked at all (`off`), and `digest.from`, the address the morning email comes from.
- `daf.env`, the keys above, if you use it.
- `pages/`, `pdf/`, `tts/` and `thumbs/`, the photos of paper pages, PDFs, read-aloud audio and the pictures of the pages you save, `fonts/`, the fonts you add, and `cache/`, manga pages that Daf can always fetch again, so a backup can skip it.
- `backups/`, the copies `daf backup` makes.

## Running it as a service

The unit I use is in `systemd/daf.service`. Copy it to `~/.config/systemd/user/`, change `WorkingDirectory` and `ExecStart` to where your copy lives, add `Environment=` lines for the variables above, and start it:

```sh
systemctl --user daemon-reload
systemctl --user enable --now daf
journalctl --user -u daf -f
```

After changing Python code, `systemctl --user restart daf`. If the service should run when you're not logged in, `loginctl enable-linger` once.

For phones, install-as-app and offline reading, Daf needs an https address. I use a Cloudflare tunnel; behind one, Daf takes the visitor's address from Cloudflare's header (only from localhost) and marks the cookie Secure.

## The `daf` command line

`bin/daf` runs the command line with the project's own Python:

| Command | Does |
|---|---|
| `daf doctor` | every source, and how fresh it is |
| `daf sync` | pulls every source now |
| `daf backup` | a checked, gzipped copy of `daf.db` in `backups/`, the last 14 kept; I run it from cron at 03:00, before the nightly backup takes the state folder |
| `daf karakeep-import [--again]` | moved the Library over from Karakeep once (notes, highlights, pictures, PDFs, and its lists as tags). Karakeep is retired now (settings `library.karakeep` is "off") |
| `daf podcasts-import` | AntennaPod's history from Nextcloud's GPodder Sync app (see [Videos and podcasts](videos-and-podcasts.md)) |
| `daf today [--json] [--date D]` | today's minutes, by source and sitting |
| `daf year 30`, `daf year 29` | the year so far |
| `daf log-paper 40` | paper minutes, with `--shabbat`, `--yesterday` or `--date D`, and `--pages N` and `--note TEXT` |
| `daf set-password [--user NAME] [--random]` | the web password, and the username |
| `daf kindle-token NAME` | a new device token, printed once |
| `daf review [--json]` | today's highlights |
| `daf morning [--send]` | the morning highlight |
| `daf note "n: text"` | a note under the morning highlight or the book on the Kindle |
| `daf voice-note FILE` | the same, from a voice note |
| `daf nightstand [ID …]` | shows or sets the three nightstand books |
| `daf paper-page PHOTO [--caption TEXT]` | a photo of a marked page into highlights |
| `daf clip "TEXT"` | a link with a time, into a transcribed clip |
| `daf jobs` | transcripts and clips, waiting or done |

`daf morning --send`, the sign-in alerts and a few warnings (a backup that failed, a morning email or a feedback note that couldn't go) send their message through a script of mine (`notify.sh`, set in `daf/cli.py` and `daf/app.py`), so point those at whatever sends messages on your server.

If you set one up and get stuck, write to me, and I'll help and fix whatever was unclear here.

<sub>Next: [How Daf runs](OPERATIONS.md) →</sub>
