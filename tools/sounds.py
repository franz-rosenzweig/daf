#!/usr/bin/env python3
"""Make Daf's own sounds for Sound (soundscape.OWN) from Creative Commons 0 recordings on Freesound.

Each pick in PICKS is one Freesound sound, where in it the loop starts and how long it is. For each one
this downloads the original (or, once Freesound's downloads for the day are used up, its preview),
cuts the stretch out, crossfades the stretch's end into its start so it loops without a seam, sets
its loudness, and saves it as a 128 kbps MP3 with PAD seconds of its own end before it and of its own
start after it (web/sound.js loops the middle). It's the way Chataltul makes the thirty Daf borrows
(its tools/fetch-sounds.py), so the two sets sound alike side by side.
The files go to STATE/sounds, with sounds.json beside them: each one's recording, who made it, its
page on Freesound and its licence.

    python3 tools/sounds.py auth                 print the link that lets this script download originals
    python3 tools/sounds.py auth <code>          swap the code that page shows for a token
    python3 tools/sounds.py make [ids]           download what's missing and write the files (all, or these)
    python3 tools/sounds.py check [ids]          read the files back: loudness, peaks, the seam, silences
    python3 tools/sounds.py try <sound> [--loop 90] [--xfade 4] [--kind nature]
                                                 how a Freesound sound would do, and where its loop should start

The key is a JSON file with client_id and client_secret from https://freesound.org/apiv2/apply (and,
after `auth`, the tokens): STATE/freesound.key, or FREESOUND_KEY=<path>. Downloads are kept in
~/.cache/daf-sounds (or SOUNDS_CACHE). Needs numpy, scipy and an ffmpeg with libmp3lame. A Daf
without these files still works: Sound just doesn't offer the ones it hasn't got.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

STATE = Path(os.environ.get("DAF_STATE", "/srv/docker/daf"))
OUT = STATE / "sounds"
KEY = Path(os.environ.get("FREESOUND_KEY", STATE / "freesound.key"))
CACHE = Path(os.environ.get("SOUNDS_CACHE", Path.home() / ".cache" / "daf-sounds"))
API = "https://freesound.org/apiv2"
UA = {"User-Agent": "daf-sounds/1.0"}
CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
SR = 48000
PAD = 0.5   # the same as PAD in web/sound.js

# How loud each kind is (LUFS, gated like BS.1770, a mono file counted as played on two speakers): the
# same as the borrowed sounds of its kind, so going from one to the other doesn't jump. Surf and crowds
# sit loudest in those, quiet rooms and the big hall's fire quietest, music in the middle.
LOUD = {"water": -19, "rain": -20, "fire": -20.5, "crowd": -18.5, "machine": -22, "nature": -22, "quiet": -24, "music": -21}

# The picks, all "Creative Commons 0" (the script checks). `kind` sets the loudness (LOUD; `lufs` sets
# it outright), `start` is where the loop begins in the recording (seconds), `loop` how long it is
# (whole seconds, which sound.js counts on), `xfade` how long its end blends into its start,
# `channels` 1 makes it mono, and `highpass` / `lowpass` (Hz) take out a rumble, hum or whine. `file`
# is the name in STATE/sounds and in soundscape.OWN. A different recording for a sound needs a new
# id, since browsers and the Mac app keep each sound by its id for good once they have it.
PICKS = {
    # Rain and storms
    'rain-tent': dict(sound=251233, kind='rain', start=156.0, loop=90, xfade=4, file='rain-tent-1'),  # "In the Tent - Rain" by pulswelle
    'rain-window': dict(sound=428605, kind='rain', start=4.9, loop=90, xfade=4, file='rain-window-1'),  # "Rain on Metal Window Ledge" by Erbsland-Music
    'tin-roof': dict(sound=673484, kind='rain', start=11.5, loop=90, xfade=4, file='tin-roof-1'),  # "Rain from hut interior, cabin, drops on metal sheet and plastic roo..." by felix.blume
    'rain-roof': dict(sound=475468, kind='rain', start=94.5, loop=90, xfade=4, file='rain-roof-1'),  # "Rain in the attic_1.wav" by o_ciz
    'rain-car': dict(sound=650774, kind='rain', start=49.0, loop=90, xfade=4, file='rain-car-1'),  # "Rain on car roof interior / Regen auf Autodach" by Borgory
    'rain-city': dict(sound=399685, kind='rain', start=44.1, loop=90, xfade=4, file='rain-city-1'),  # "Summer rain on quiet city street" by tarasyoung
    'rain-leaves': dict(sound=383064, kind='rain', start=179.9, loop=90, xfade=4, file='rain-leaves-1'),  # "ForestRainShower1a.mp3" by AlanCat
    'gutter': dict(sound=652260, kind='rain', start=68.3, loop=90, xfade=4, file='gutter-1'),  # "Rain gutter zleb 003.wav" by frenkfurth
    'drips': dict(sound=459983, kind='rain', start=99.4, loop=90, xfade=4, file='drips-1'),  # "Rain Water Dripping Softly" by florianreichelt
    'storm-trees': dict(sound=204239, kind='rain', start=154.1, loop=90, xfade=4, file='storm-trees-1'),  # "Wind in the Trees, Storm 3" by timsc
    'storm-tent': dict(sound=510248, kind='nature', start=45.0, loop=90, xfade=4, file='storm-tent-1'),  # "Rain and Wind Inside tent on campsite_Patagonia El Chalten.wav" by Singular_Estudio
    'umbrella': dict(sound=330291, kind='rain', start=14.2, loop=90, xfade=4, file='umbrella-1'),  # "EXT Rain on umbrella 2.wav" by deleted_user_2104797
    # Wind, snow and sand
    'wind-trees': dict(sound=466122, kind='nature', start=202.0, loop=90, xfade=4, file='wind-trees-1'),  # "Windy night trees rustling heavy.wav" by franciscopcoutinho
    'wind-grass': dict(sound=215853, kind='nature', start=8.3, loop=90, xfade=4, file='wind-grass-1'),  # "Wind blowing in dry grass, in a field in Texas, USA." by felix.blume
    'reeds': dict(sound=795323, kind='nature', start=80.0, loop=90, xfade=4, file='reeds-1'),  # "wind in the reeds" by Garuda1982
    'mountain': dict(sound=725630, kind='nature', start=7.1, loop=90, xfade=4, file='mountain-1'),  # "Larrun_Mountains_MedWind" by nicotep
    'desert-wind': dict(sound=147512, kind='nature', start=10.2, loop=90, xfade=4, file='desert-wind-1'),  # "Wind blowing and howling in a plastic bottle, in the desert of Chile." by felix.blume
    'sandstorm': dict(sound=632771, kind='nature', start=129.0, loop=90, xfade=4, file='sandstorm-1'),  # "Sandstorm Looping" by gbayles
    'polar-wind': dict(sound=450142, kind='nature', start=56.0, loop=90, xfade=4, file='polar-wind-1'),  # "air tone arctic wind blowing, distant water tone lowcut Quaqtaq, Nu..." by kyles
    'snowfall': dict(sound=719961, kind='nature', start=56.1, loop=90, xfade=4, file='snowfall-1'),  # "Snowfall Ambience, City" by Kinoton
    'autumn': dict(sound=712704, kind='nature', start=128.9, loop=90, xfade=4, file='autumn-1'),  # "Quiet cold autumn woods MIXPRE3 BP4025 NOVEMBER 28 2023" by kvgarlic
    'barn-wind': dict(sound=577498, kind='nature', start=42.9, loop=90, xfade=4, file='barn-wind-1'),  # "120621 Wind, barn interior, stong, creaks, rattles BLYTH.flac" by TRP
    # Water
    'river': dict(sound=752246, kind='water', start=107.6, loop=90, xfade=4, file='river-1'),  # "AMBIENCE-EXTERIOR-EVENING-FRIAS_EBRO_RIVER-LIGHT_STREAM-4824-01" by pblzr
    'waterfall': dict(sound=650699, kind='water', start=22.9, loop=90, xfade=4, file='waterfall-1'),  # "Waterfall_Meraner_Höhenweg_01_160922.wav" by datapopstar2
    'lake': dict(sound=757960, kind='water', start=202.8, loop=90, xfade=4, file='lake-1'),  # "Gentle Waves on the Lake with Serene Atmosphere" by Garuda1982
    'pebbles': dict(sound=656586, kind='water', start=19.5, loop=90, xfade=4, file='pebbles-1'),  # "Sound pebble beach ambient" by Arkolt
    'canal': dict(sound=449721, start=2.4, loop=90, xfade=4, lufs=-22, file='canal-1'),  # "Venezia Canal Grande early morning" by emanuele.caro
    'fountain': dict(sound=460559, kind='water', start=11.7, loop=90, xfade=4, file='fountain-1'),  # "fountain_ambience_2_courtyard_abbey_gardens_stereo.wav" by nickmaysoundmusic
    'watermill': dict(sound=263583, kind='water', start=0.0, loop=73, xfade=4, file='watermill-1'),  # "Watermill.wav" by Berwitz
    'underwater': dict(sound=482167, kind='water', start=17.0, loop=90, xfade=4, file='underwater-1'),  # "Underwater Ambience.wav" by Tim_Verberne
    'cave': dict(sound=636109, kind='quiet', start=147.4, loop=90, xfade=4, file='cave-1'),  # "ambience cave6.ogg" by fonografico
    'sea-cave': dict(sound=196713, kind='quiet', start=202.5, loop=90, xfade=4, file='sea-cave-1'),  # "Sea Cave" by Andy_Gardner
    # Ships and the sea
    'ship': dict(sound=195193, kind='machine', start=71.0, loop=90, xfade=4, file='ship-1'),  # "LargeWoodenShip.mp3" by PimFeijen
    'engine-room': dict(sound=578478, kind='machine', start=10.2, loop=90, xfade=4, file='engine-room-1'),  # "Ferry Boat Ambience2" by Sotiris_Laskaris
    'sailing': dict(sound=760339, kind='water', start=96.9, loop=90, xfade=4, file='sailing-1'),  # "sailboat front cabine" by bruno.auzet
    'rowing': dict(sound=509323, kind='water', start=0.1, loop=86, xfade=4, file='rowing-1'),  # "Kayaking in calm weather" by AugustSandberg
    'harbour': dict(sound=561815, kind='water', start=13.4, loop=90, xfade=4, file='harbour-1'),  # "Genaral Habour Ambience" by Kinoton
    'gulls': dict(sound=785882, kind='nature', start=14.0, loop=90, xfade=4, file='gulls-1'),  # "seagulls pipits and waves "ile aux vaches" 7" by bruno.auzet
    'river-boat': dict(sound=636078, kind='machine', start=8.0, loop=90, xfade=4, file='river-boat-1'),  # "River Boat Engine - Wailua River (Hawaii)" by coalcon
    'rigging': dict(sound=360633, kind='nature', start=20.9, loop=90, xfade=4, file='rigging-1'),  # "Stronger wind at a marina, rattling at masts and rigging of the yac..." by Pfannkuchn
    # Getting around
    'train': dict(sound=827222, kind='machine', start=65.1, loop=90, xfade=4, file='train-1'),  # "🚆 Polish Train Ambience 🔊 Soundscape from Inside the Carriage 🌍 Som..." by GirlWithSoundRecorder
    'steam-train': dict(sound=438769, kind='machine', start=4.6, loop=90, xfade=4, file='steam-train-1'),  # "G48-01-Steam Train Int Ambience.wav" by craigsmith
    'station': dict(sound=785385, kind='crowd', start=29.8, loop=90, xfade=4, file='station-1'),  # "AMBIENCE_INTERIOR_TRAIN-STATION-LISBOA_GARE-DO-ORIENTE_4824_01" by pblzr
    'subway': dict(sound=213891, kind='machine', start=32.2, loop=90, xfade=4, file='subway-1'),  # "London Underground: full train journey through tunnel" by peridactyloptrix
    'bus': dict(sound=261289, kind='machine', start=92.9, loop=90, xfade=4, file='bus-1'),  # "Bus Ride" by FairhavenCollection
    'car': dict(sound=685074, kind='machine', start=17.0, loop=90, xfade=4, file='car-1'),  # "Car driving on asphalt road in the desert with closed window, recor..." by felix.blume
    'airplane': dict(sound=456092, kind='machine', start=33.4, loop=90, xfade=4, file='airplane-1'),  # "Airplane cabin ambience / atmosphere Airbus A330-300" by FillSoko
    'carriage': dict(sound=121129, kind='machine', start=416.6, loop=90, xfade=4, file='carriage-1'),  # "horses-and-carriage.wav" by ondrosik
    'spaceship': dict(sound=614461, kind='quiet', start=28.3, loop=90, xfade=4, file='spaceship-1'),  # "17. flying spaceship interior (roomtone)" by secondbody
    'tram': dict(sound=32840, kind='machine', start=109.5, loop=90, xfade=4, file='tram-1'),  # "streetcarstereo.wav" by moxobna
    # Towns and crowds
    'city-day': dict(sound=835887, kind='crowd', start=41.0, loop=90, xfade=4, file='city-day-1'),  # "Daytime City Ambience" by Artem_Zaitsev
    'road': dict(sound=383211, kind='machine', start=32.8, loop=90, xfade=4, file='road-1'),  # "Light Traffic with Birds" by Kinoton
    'market': dict(sound=659634, kind='crowd', start=22.0, loop=90, xfade=4, file='market-1'),  # "2022-11-12-binaural-london-market-ambience.wav" by ilmari_freesound
    'bazaar': dict(sound=819223, kind='crowd', start=18.1, loop=90, xfade=4, file='bazaar-1'),  # "Evening Bazaar Ambience at Souq Al Bashorah, Ramallah – Palestine" by sounds_from_palestine
    'fair': dict(sound=635159, kind='crowd', start=57.2, loop=90, xfade=4, file='fair-1'),  # "Fairground Ambience" by HECKFRICKER
    'pub': dict(sound=383265, kind='crowd', start=49.3, loop=90, xfade=4, file='pub-1'),  # "Busy Bar Ambience" by deleted_user_7146007
    'big-crowd': dict(sound=459161, kind='crowd', start=263.4, loop=90, xfade=4, file='big-crowd-1'),  # "AMBLM ext day people crowd walla berlin kulturforum international g..." by LudwigMueller
    'party': dict(sound=878047, kind='crowd', start=116.8, loop=90, xfade=4, lowpass=900, file='party-1'),  # "adult_crowd_ambiance_03" by joedeshon
    'museum': dict(sound=569166, kind='quiet', start=38.4, loop=90, xfade=4, file='museum-1'),  # "Museum Ambience" by gravity_proof
    'fireworks': dict(sound=456313, kind='crowd', start=15.9, loop=90, xfade=4, file='fireworks-1'),  # "firework distant in teh town.WAV" by cupido-1
    # Rooms and buildings
    'church-bells': dict(sound=622816, kind='quiet', start=295.6, loop=90, xfade=4, file='church-bells-1'),  # "Church bells for Ukraine 220302_033.flac" by klankbeeld
    'cathedral': dict(sound=715662, kind='quiet', start=44.9, loop=90, xfade=4, file='cathedral-1'),  # "130516 Church interior, St Patrick's Cathedral, doors open close wh..." by TRP
    'prayer-hall': dict(sound=453902, kind='crowd', start=21.6, loop=90, xfade=4, file='prayer-hall-1'),  # "crowd int large busy echo church2.flac" by kyles
    'library': dict(sound=620683, kind='quiet', start=103.7, loop=90, xfade=4, file='library-1'),  # "Quiet library ambience" by xkeril
    'clock': dict(sound=242008, kind='quiet', start=306.9, loop=90, xfade=4, file='clock-1'),  # "Clock Ticking.wav" by photogtony
    'quiet-flat': dict(sound=398843, kind='quiet', start=30.9, loop=90, xfade=4, file='quiet-flat-1'),  # "170720_SmallAppartment_Kitchen_F.wav" by blaukreuz
    'hall': dict(sound=171462, kind='quiet', start=32.2, loop=90, xfade=4, file='hall-1'),  # "people ambience large hall 02.wav" by klankbeeld
    'hospital': dict(sound=201637, kind='quiet', start=22.4, loop=90, xfade=4, file='hospital-1'),  # "Hospital corridor" by bassboybg
    'hotel': dict(sound=747196, kind='crowd', start=132.4, loop=90, xfade=4, file='hotel-1'),  # "220130_Asuncion_LobbyHotelGuarani_Morning" by blaukreuz
    'prison': dict(sound=165261, kind='quiet', start=49.3, loop=90, xfade=4, file='prison-1'),  # "Walla of brazilian jail - 01" by jmbphilmes
    'kitchen': dict(sound=633804, kind='fire', start=18.0, loop=90, xfade=4, file='kitchen-1'),  # "Frying Bacon" by Urkki69
    'fan': dict(sound=452485, kind='quiet', start=0.5, loop=90, xfade=4, file='fan-1'),  # "electric fan buzz hum close +shut off blade spin.flac" by kyles
    'pencil': dict(sound=388874, start=8.0, loop=90, xfade=4, lufs=-27, file='pencil-1'),  # "Writing with pencil" by vladnegrila
    'tunnel': dict(sound=475476, kind='quiet', start=22.0, loop=90, xfade=4, file='tunnel-1'),  # "Tunnel_1(rain, dripping water, wind).wav" by o_ciz
    # Work
    'machine-hall': dict(sound=353159, kind='quiet', start=78.2, loop=90, xfade=4, file='machine-hall-1'),  # "Room Tone, Sci Fi, Large Hall" by Kinoton
    'factory': dict(sound=588361, kind='machine', start=73.6, loop=90, xfade=4, file='factory-1'),  # "FACTORY 4.wav" by indieground
    'forge': dict(sound=395887, kind='fire', start=7.8, loop=90, xfade=4, file='forge-1'),  # "starting fire in blacksmith.wav" by jokallset
    'printing-press': dict(sound=440127, kind='machine', start=79.1, loop=90, xfade=4, file='printing-press-1'),  # "180619_BerlinKoenigsdruck_WA_FrontHall_ST.wav" by blaukreuz
    'workshop': dict(sound=520467, kind='quiet', start=37.0, loop=90, xfade=4, file='workshop-1'),  # "BGSaSc Room Tone Workshop Birds Hum Clock Ticking" by Profispiesser
    'typewriter': dict(sound=519622, kind='quiet', start=50.0, loop=90, xfade=4, file='typewriter-1'),  # "supersuper_Typewriter.wav" by supersupernator
    # Woods, fields and animals
    'frogs': dict(sound=387868, kind='nature', start=182.2, loop=90, xfade=4, file='frogs-1'),  # "Frogs Toads April 10 2017.wav" by Danjocross
    'pond-night': dict(sound=412942, kind='nature', start=66.9, loop=90, xfade=4, file='pond-night-1'),  # "Lake at night 1.aif" by i_luv_soundz
    'owl': dict(sound=559100, kind='nature', start=27.5, loop=90, xfade=4, file='owl-1'),  # "Owl at night" by saralana
    'cicadas': dict(sound=812287, kind='nature', start=9.0, loop=90, xfade=4, file='cicadas-1'),  # "Cariati Campagna Ore 12" by Paddoa
    'heat': dict(sound=648241, kind='nature', start=26.9, loop=90, xfade=4, file='heat-1'),  # "HotSummerAfternoonField  smaller file AUGUST 25 2022.WAV" by kvgarlic
    'bees': dict(sound=567548, kind='nature', start=94.1, loop=90, xfade=4, file='bees-1'),  # "Beehive recording from very close (Switzerland)" by felix.blume
    'jungle-day': dict(sound=450532, kind='nature', start=21.9, loop=90, xfade=4, file='jungle-day-1'),  # "Amazon jungle day crickets birds and frogs from boat on river great..." by kyles
    'evening': dict(sound=665159, kind='nature', start=92.6, loop=90, xfade=4, file='evening-1'),  # "Countryside during evening in Missouri in a field, some birds singi..." by felix.blume
    'night-farm': dict(sound=819503, kind='nature', start=80.0, loop=90, xfade=4, file='night-farm-1'),  # "Night ambience near a farm" by LukaCafuka
    'crows': dict(sound=168108, kind='nature', start=124.1, loop=90, xfade=4, file='crows-1'),  # "Birdsong and crows in fog.aiff" by andymanister
    'loons': dict(sound=751848, kind='nature', start=0.0, loop=78, xfade=4, file='loons-1'),  # "Late Summer Loons" by itinerantmonk108
    'sheep': dict(sound=67183, kind='nature', start=48.0, loop=90, xfade=4, file='sheep-1'),  # "2008-01-22 18_13_58 - Casa del Campo (Madrid), Spain_MP3_192.mp3" by notthisbody
    'farmyard': dict(sound=435671, kind='nature', start=20.2, loop=90, xfade=4, file='farmyard-1'),  # "Farm ambience_1.wav" by YellowJacketStudios
    'wolves': dict(sound=651193, kind='nature', start=1.9, loop=90, xfade=4, file='wolves-1'),  # "Wolfes howl howling Wolf Pack heulen" by Borgory
    'cowbells': dict(sound=700525, kind='nature', start=57.1, loop=90, xfade=4, file='cowbells-1'),  # "salers cowbells.wav" by bruno.auzet
    # Music
    'piano': dict(sound=703137, kind='music', start=37.0, loop=120, xfade=8, file='piano-1'),  # "Ambient Piano Guitar Texture E" by deadrobotmusic
    'melancholy': dict(sound=868507, kind='music', start=2.4, loop=120, xfade=8, file='melancholy-1'),  # "delicate melancholic cinematic underscore, understated family confl..." by shqiptarbas
    'guitar': dict(sound=877547, kind='music', start=127.3, loop=120, xfade=8, file='guitar-1'),  # "Slowly Evolving Guitar Ambient Soundscape in C Major" by bassimat
    'harp': dict(sound=701545, kind='music', start=3.9, loop=120, xfade=8, file='harp-1'),  # "julyspacestar.wav" by mountainear
    'choir': dict(sound=808032, kind='music', start=14.8, loop=120, xfade=8, file='choir-1'),  # "Ambient F Sharp Minor Ethereal Choir Pad 1" by deadrobotmusic
    'drone': dict(sound=854865, kind='music', start=159.5, loop=120, xfade=8, file='drone-1'),  # "Infinite Cathedral Sacred Drone by Mantice" by bassimat
    'warm-drone': dict(sound=854842, kind='music', start=63.3, loop=120, xfade=8, file='warm-drone-1'),  # "Warm Pad Essentials Drone by Mantice" by bassimat
    'dread': dict(sound=368146, kind='music', start=115.2, loop=120, xfade=8, file='dread-1'),  # "Tension Drones" by Vospi
    'organ': dict(sound=321772, kind='music', start=8.4, loop=120, xfade=8, file='organ-1'),  # "Traditional Church Organ Music [Florence - Italy] 01" by Skjor1
}


# ---------- Freesound ----------
def key():
    try:
        return json.loads(KEY.read_text())
    except FileNotFoundError:
        sys.exit(f"No key at {KEY}. Get one at https://freesound.org/apiv2/apply.")


def save_key(k):
    tmp = KEY.with_suffix(".tmp")
    old = os.umask(0o077)
    try:
        tmp.write_text(json.dumps(k))
    finally:
        os.umask(old)
    os.chmod(tmp, 0o600)
    os.replace(tmp, KEY)


def token(k, **form):
    data = urllib.parse.urlencode({"client_id": k["client_id"], "client_secret": k["client_secret"], **form}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request(f"{API}/oauth2/access_token/", data=data, headers=UA), timeout=30))
    k.update(access_token=r["access_token"], refresh_token=r["refresh_token"], expires_at=int(time.time()) + int(r.get("expires_in", 86400)))
    save_key(k)


def bearer(k):
    """The OAuth2 token for downloading originals, refreshed when it's run out."""
    if "refresh_token" not in k:
        sys.exit("Downloading originals needs a sign-in: run `tools/sounds.py auth` first.")
    if time.time() > k.get("expires_at", 0) - 300:
        token(k, grant_type="refresh_token", refresh_token=k["refresh_token"])
    return k["access_token"]


class Limit(Exception):
    """Freesound's limit for the day is used up (500 downloads of originals, 2000 other calls)."""


def get(url, k, auth=False, tries=4):
    """A GET to the API, slowly enough for its 60 a minute (30 for downloads)."""
    head = dict(UA)
    if auth:
        head["Authorization"] = f"Bearer {bearer(k)}"
    else:
        url += ("&" if "?" in url else "?") + "token=" + k["client_secret"]
    for i in range(tries):
        time.sleep(2.1 if auth else 1.1)
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=300)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            if "/day" in e.read().decode(errors="replace"):
                raise Limit() from e           # waiting won't help today, and each try counts
            time.sleep(15 * (i + 1))


def info(k, sound):
    f = CACHE / f"{sound}.json"
    if f.exists():
        return json.loads(f.read_text())
    fields = "id,name,username,url,license,duration,channels,samplerate,type,description,tags,previews"
    r = json.load(get(f"{API}/sounds/{sound}/?fields={fields}", k))
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(r))
    return r


_limited = False


def download(k, sound, secs=None):
    """The recording and which it is: the original (downloaded once into CACHE, with a sign-in), or,
    when Freesound's downloads for the day are used up, its high-quality preview, an OGG (enough of
    it for `secs` seconds, or all of it)."""
    global _limited
    meta = info(k, sound)
    if meta["license"] != CC0:
        sys.exit(f"{sound} isn't CC0 ({meta['license']}).")
    f = CACHE / f"{sound}.original.{meta['type']}"
    if f.exists():
        return f, "original"
    if not _limited:
        try:
            r = get(f"{API}/sounds/{sound}/download/", k, auth=True)
            tmp = f.with_suffix(".part")
            with open(tmp, "wb") as o:
                while chunk := r.read(1 << 20):
                    o.write(chunk)
            tmp.replace(f)
            return f, "original"
        except Limit:
            _limited = True
            print("Freesound's downloads for today are used up, so the previews it is", file=sys.stderr)
    return preview(meta, secs), "preview"


def preview(meta, secs=None):
    """Freesound's high-quality preview of a sound (an OGG, no sign-in needed, but served slowly), kept
    in CACHE: the first part of it, enough for `secs` seconds, or all of it. A later call that needs
    more fetches the rest onto the end."""
    url = meta["previews"]["preview-hq-ogg"]
    f, note = CACHE / f"{meta['id']}.preview.ogg", CACHE / f"{meta['id']}.preview.json"
    have = json.loads(note.read_text()) if note.exists() and f.exists() else {"bytes": 0, "total": None}
    if have["total"] is None:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=60) as r:
            have["total"] = int(r.headers["Content-Length"])
    total = have["total"]
    want = total if not secs else min(total, int(total * (secs + 5) / max(1.0, float(meta["duration"]))) + 65536)
    if have["bytes"] < want:
        req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={have['bytes']}-{want - 1}"})
        if have["bytes"]:
            os.truncate(f, have["bytes"])                # what an interrupted fetch left after it goes
        with urllib.request.urlopen(req, timeout=600) as r, open(f, "ab" if have["bytes"] else "wb") as o:
            while chunk := r.read(1 << 16):
                o.write(chunk)
        have["bytes"] = f.stat().st_size
        note.write_text(json.dumps(have))
    return f


# ---------- audio in and out ----------
def channels_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return 1 if out == "1" else 2


def decode(path, channels=None, secs=None, sr=SR):
    """An audio file → float32 array (channels, samples) at `sr`, the first `secs` of it."""
    channels = channels or channels_of(path)
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path)] + (["-t", str(secs)] if secs else []) +
                         ["-ac", str(channels), "-ar", str(sr), "-f", "f32le", "pipe:1"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, channels).T.copy()


def encode_mp3(x, sr=SR, kbps=128):
    pcm = np.ascontiguousarray(np.clip(x, -1, 1).T, np.float32).tobytes()
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", str(len(x)), "-i", "pipe:0",
                           "-c:a", "libmp3lame", "-b:a", f"{kbps}k", "-f", "mp3", "pipe:1"], input=pcm, capture_output=True, check=True).stdout


# ---------- loudness (ITU-R BS.1770: K-weighting and gating) ----------
def kweight(x, sr):
    from scipy.signal import lfilter

    def shelf(G=3.999843853973347, Q=0.7071752369554196, fc=1681.974450955533):
        A = 10 ** (G / 40); w = 2 * np.pi * fc / sr; a = np.sin(w) / (2 * Q); c = np.cos(w)
        b = [A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * a), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * a)]
        d = [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * a, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * a]
        return np.array(b) / d[0], np.array(d) / d[0]

    def highpass(Q=0.5003270373238773, fc=38.13547087602444):
        w = 2 * np.pi * fc / sr; a = np.sin(w) / (2 * Q); c = np.cos(w)
        b = np.array([(1 + c) / 2, -(1 + c), (1 + c) / 2]); d = np.array([1 + a, -2 * c, 1 - a])
        return b / d[0], d / d[0]
    for b, a in (shelf(), highpass()):
        x = lfilter(b, a, x, axis=-1)
    return x


def power(x, sr):
    """The K-weighted power of a (channels, n) signal, summed over its channels; a mono one counts as
    played on two speakers, the way Web Audio plays a mono buffer, so mono and stereo compare fairly."""
    return (kweight(x, sr) ** 2).sum(0) * (2 if len(x) == 1 else 1)


def blocks(x, sr, win=0.4, hop=0.1, pw=None):
    """Loudness of each window (LUFS) of a (channels, n) signal (or of its `power`, worked out once)."""
    pw = power(x, sr) if pw is None else pw
    n, h = int(win * sr), int(hop * sr)
    c = np.concatenate([[0], np.cumsum(pw)])
    starts = np.arange(0, len(pw) - n + 1, h)
    return -0.691 + 10 * np.log10(np.maximum((c[starts + n] - c[starts]) / n, 1e-12))


def lufs(x, sr):
    """Integrated loudness, gated like BS.1770 (-70 LUFS, then 10 under the mean)."""
    v = blocks(x, sr)
    v = v[v > -70]
    if not len(v):
        return -70.0
    mean = lambda u: 10 * np.log10(np.mean(10 ** (u / 10)))  # noqa: E731
    return float(mean(v[v > mean(v) - 10]))


# ---------- making a loop ----------
def loop_of(x, sr, start, loop, xfade):
    """The stretch [start, start + loop) of x, with what comes after it crossfaded into its first
    `xfade` seconds, so its last sample runs on into its first. A recording that slowly gets louder
    or softer gets a gentle tilt first, so its two ends are equally loud and the loop doesn't step
    where it wraps. The fade keeps the power steady for however alike the two bits are."""
    s, L, X = int(start * sr), int(loop * sr), int(xfade * sr)
    if s + L + X > x.shape[1]:
        sys.exit(f"The recording is {x.shape[1] / sr:.0f}s; that needs {(s + L + X) / sr:.0f}s.")
    x = x[:, s:s + L + X].copy()
    W = max(X, 3 * sr)
    tilt = lufs(x[:, :W], sr) - lufs(x[:, L:L + W] if L + W <= x.shape[1] else x[:, L - W + X:L + X], sr)
    x *= 10 ** ((tilt * (np.arange(x.shape[1]) / L - 0.5)) / 20)
    head, tail = x[:, :X], x[:, L:L + X]
    r = float(np.sum(head * tail) / np.sqrt(np.sum(head ** 2) * np.sum(tail ** 2) + 1e-12))
    p = 0.5 - 0.5 * np.cos(np.pi * (np.arange(X) + 0.5) / X)
    a, b = 1 - p, p
    norm = np.sqrt(a * a + b * b + 2 * max(r, -0.6) * a * b)
    y = x[:, :L].copy()
    y[:, :X] = (tail * a + head * b) / norm
    return y, r, tilt


def limit(y, sr, ceiling=0.89):
    """A limiter for the odd loud crackle, splash or click, worked out around the loop (so the seam
    stays seamless): it comes down 5 ms early and back in 60 ms."""
    hop = sr // 1000
    n = y.shape[1] // hop * hop
    peak = np.abs(y[:, :n]).max(0).reshape(-1, hop).max(1)
    want = np.tile(np.minimum(1, ceiling / np.maximum(peak, 1e-9)), 3)
    look = 5
    want = np.min(np.lib.stride_tricks.sliding_window_view(np.concatenate([want, np.ones(look)]), look + 1), axis=1)
    g = np.empty_like(want); v = 1.0; rel = 1 - np.exp(-1 / 60)
    for i, w in enumerate(want):
        v = w if w < v else v + rel * (w - v)
        g[i] = v
    g = g[len(g) // 3: 2 * len(g) // 3]
    gs = np.interp(np.arange(y.shape[1]), np.arange(len(g)) * hop + hop / 2, g, period=y.shape[1])
    return y * gs, float(g.min()), float(np.mean(g < 10 ** (-1 / 20)))


def padded(y, sr):
    p = int(PAD * sr)
    return np.concatenate([y[:, -p:], y, y[:, :p]], axis=1)


def target(pick):
    return float(pick["lufs"]) if "lufs" in pick else LOUD[pick["kind"]]


def render(path, pick):
    """The finished loop (channels, samples) from a recording, and what happened on the way."""
    from scipy.signal import butter, sosfilt
    xfade = pick.get("xfade", 4)
    x = decode(path, pick.get("channels"), secs=pick["start"] + pick["loop"] + xfade + 1)
    for band in ("highpass", "lowpass"):
        if pick.get(band):
            x = sosfilt(butter(4, pick[band], band, fs=SR, output="sos"), x, axis=-1).astype(np.float32)
    y, r, tilt = loop_of(x, SR, pick["start"], pick["loop"], xfade)
    want = target(pick)
    y *= 10 ** ((want - lufs(y, SR)) / 20)
    y, g, busy = limit(y, SR)
    y *= 10 ** ((want - lufs(y, SR)) / 20)
    for _ in range(4):
        if np.abs(y).max() <= 0.98:
            break
        y, g, busy = limit(y, SR)
        y *= 10 ** ((want - lufs(y, SR)) / 20)
    if np.abs(y).max() > 0.98:
        y, g, busy = limit(y, SR)
    return y, {"ends_alike": round(r, 2), "tilt_db": round(tilt, 1), "lufs": round(want, 1),
               "limiter_db": round(20 * np.log10(g), 1), "limiter_busy": round(busy, 4)}


def make(id, k, manifest):
    pick = PICKS[id]
    path, kind = download(k, pick["sound"], secs=pick["start"] + pick["loop"] + pick.get("xfade", 4) + 2)
    y, how = render(path, pick)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{pick['file']}.mp3"
    tmp = f.with_suffix(".part")
    tmp.write_bytes(encode_mp3(padded(y, SR)))
    tmp.replace(f)
    m = info(k, pick["sound"])
    manifest[id] = {"file": f.name, "freesound": pick["sound"], "name": m["name"], "by": m["username"], "url": m["url"],
                    "licence": "CC0 1.0 (public domain)", "licence_url": CC0, "start": pick["start"], "loop": pick["loop"],
                    "channels": len(y), "lufs": how["lufs"], "made_from": kind}
    print(f"{id:14} {f.name:20} from {pick['sound']} ({kind}) {pick['start']}s+{pick['loop']}s, {len(y)}ch, tilted {how['tilt_db']:+.1f} dB, "
          f"ends alike {how['ends_alike']:+.2f}, {how['lufs']:.1f} LUFS, limiter at most {how['limiter_db']:.1f} dB, {f.stat().st_size / 1e6:.2f} MB")


def save_manifest(manifest):
    f = OUT / "sounds.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"about": "Daf's own sounds for Sound, made by tools/sounds.py from Creative Commons 0 recordings on Freesound",
                               "made": time.strftime("%Y-%m-%d"), "sounds": dict(sorted(manifest.items()))}, indent=1, ensure_ascii=False))
    tmp.replace(f)


# ---------- checking the files ----------
def seam(y, sr):
    """The loop's wrap against the rest: the jump from its last sample to its first against the usual
    step, and the loudness and spectrum either side of the wrap against any two neighbouring moments."""
    m = y.mean(0)
    step = np.abs(np.diff(m))
    jump = abs(m[0] - m[-1]) / (np.percentile(step, 99) + 1e-12)
    w = int(0.25 * sr)
    spec = lambda a: np.log(np.abs(np.fft.rfft(a * np.hanning(len(a)))) + 1e-9)  # noqa: E731
    lvl = lambda a: 10 * np.log10(np.mean(a ** 2) + 1e-12)  # noqa: E731
    pairs = [(m[i - w:i], m[i:i + w]) for i in range(w, len(m) - w, w)]
    sd = [np.mean(np.abs(spec(a) - spec(b))) for a, b in pairs]
    ld = [abs(lvl(a) - lvl(b)) for a, b in pairs]
    a, b = m[-w:], m[:w]
    return jump, abs(lvl(a) - lvl(b)), float(np.percentile(ld, 95)), float(np.mean(np.abs(spec(a) - spec(b)))), float(np.percentile(sd, 95))


def silences(path, db=-50, secs=1.0):
    """Stretches quieter than `db` dBFS for `secs` or more (ffmpeg's silencedetect)."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", f"silencedetect=noise={db}dB:d={secs}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return err.count("silence_end")


def measure(path):
    """What `check` prints for one file, as a dict."""
    x = decode(path)
    L = round(x.shape[1] / SR - 2 * PAD)
    y = x[:, int(PAD * SR):int(PAD * SR) + L * SR]
    jump, ldiff, lp95, sdiff, sp95 = max((seam(x[:, int(PAD * SR) - d:int(PAD * SR) - d + L * SR], SR) for d in (0, 1105, 2257)),
                                        key=lambda v: v[0] + v[1] / max(v[2], 0.1) + v[3] / v[4])
    pw = power(y, SR)
    st, mo = blocks(y, SR, 3, 1, pw), blocks(y, SR, 0.4, 0.1, pw)
    return {"loop": L, "channels": len(x), "lufs": round(lufs(y, SR), 1), "peak_db": round(float(20 * np.log10(np.abs(y).max() + 1e-12)), 1),
            "spread_db": round(float(np.percentile(st, 95) - np.percentile(st, 5)), 1),
            "loudest_db": round(float(mo.max() - np.median(st)), 1),
            "seam": [round(float(jump), 2), round(float(ldiff), 1), round(lp95, 1), round(float(sdiff), 2), round(sp95, 2)],
            "silences": silences(path)}


def check(ids):
    print("id             loop  ch   LUFS  peak  spread  loudest  silences  seam: jump/step, level dB (p95), spectrum (p95)")
    for id in ids:
        f = OUT / f"{PICKS[id]['file']}.mp3"
        if not f.exists():
            print(f"{id:14} missing")
            continue
        m = measure(f)
        j, ld, lp, sd, sp = m["seam"]
        print(f"{id:14} {m['loop']:4}s  {m['channels']}  {m['lufs']:6.1f} {m['peak_db']:5.1f}  {m['spread_db']:5.1f}  {m['loudest_db']:+6.1f}   {m['silences']:4}      "
              f"{j:4.2f}, {ld:4.1f} ({lp:4.1f}), {sd:4.2f} ({sp:4.2f})")


# ---------- trying a recording ----------
def suggest(path, loop, xfade=4, secs=900):
    """Where in a recording a loop would sit best: a steady stretch with nothing much louder than the
    rest, whose two ends are alike in loudness and, for something with a rhythm, in step. Best first:
    [(start, spread dB, loudest moment over the median dB, ends differ dB, in step)]."""
    from numpy.lib.stride_tricks import sliding_window_view as win
    x = decode(path, None, secs=secs)
    pw = power(x, SR)
    st, mo, env = blocks(x, SR, 3, 1, pw), blocks(x, SR, 0.4, 0.1, pw), blocks(x, SR, 0.05, 0.01, pw)
    X1, X100 = max(1, round(xfade)), int(xfade * 100)
    n = int((x.shape[1] / SR - loop - max(xfade, 3) - 1) * 10)      # starts, every tenth of a second
    n = min(n, (len(st) - loop - X1 + 1) * 10, len(mo) - loop * 10 + 1, (len(env) - loop * 100 - X100) // 10 + 1)
    if n <= 0:
        return
    W = win(st, loop)                                                # by whole seconds, as the start's int()
    spread_s = np.percentile(W, 95, axis=1) - np.percentile(W, 5, axis=1)
    median_s = np.median(W, axis=1)
    ends_s = np.abs(win(st, X1).mean(1)[:len(st) - loop - X1 + 1] - win(st, X1).mean(1)[loop:loop + len(st) - loop - X1 + 1])
    sec = np.arange(n) // 10
    spread, ends = spread_s[sec], ends_s[sec]
    events = win(mo, loop * 10).max(1)[:n] - median_s[sec]
    H = win(env, X100)[::10][:n]
    T = win(env, X100)[loop * 100::10][:n]
    H = H - H.mean(1, keepdims=True); T = T - T.mean(1, keepdims=True)
    den = np.sqrt((H ** 2).sum(1) * (T ** 2).sum(1))
    step = np.where(den > 0, (H * T).sum(1) / np.maximum(den, 1e-12), 0.0)
    score = spread + 0.5 * ends + 0.4 * np.maximum(0, events - 5) - 2 * step
    shown = []
    for i in np.argsort(score):
        s = i / 10
        if any(abs(s - o) < 5 for o in shown):
            continue
        shown.append(s)
        yield float(s), float(spread[i]), float(events[i]), float(ends[i]), float(step[i])
        if len(shown) == 6:
            break


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd == "check":
        return check(rest or list(PICKS))
    k = key()
    if cmd == "auth":
        if rest:
            token(k, grant_type="authorization_code", code=rest[0])
            print("Signed in; the token is in", KEY)
        else:
            print(f"Open this, press Authorize, and run `auth <code>` with the code it shows:\n{API}/oauth2/authorize/?client_id={k['client_id']}&response_type=code")
    elif cmd == "make":
        f = OUT / "sounds.json"
        manifest = json.loads(f.read_text())["sounds"] if f.exists() else {}
        manifest = {i: v for i, v in manifest.items() if i in PICKS}
        try:
            for id in rest or PICKS:
                make(id, k, manifest)
        finally:
            save_manifest(manifest)
    elif cmd == "try":
        loop, xfade, kind = 90, 4.0, "nature"
        for flag in ("--loop", "--xfade", "--kind"):
            if flag in rest:
                i = rest.index(flag)
                v = rest[i + 1]
                del rest[i:i + 2]
                if flag == "--loop":
                    loop = int(v)
                elif flag == "--xfade":
                    xfade = float(v)
                else:
                    kind = v
        sound = int(rest[0])
        m = info(k, sound)
        path, got = download(k, sound, secs=600)
        print(f"{sound} {m['name']!r} by {m['username']} ({got}), {m['duration']:.0f}s, {m['samplerate']} Hz, {m['license'].split('/')[-3]}")
        for s, spread, events, ends, step in suggest(path, loop, xfade, secs=600):
            print(f"  start {s:6.1f}s: spread {spread:4.1f} dB, loudest moment +{events:4.1f} dB, ends differ {ends:3.1f} dB, in step {step:+.2f}")
        print(f"  as a {kind}: {LOUD[kind]} LUFS")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
