<sub>[Daf docs](README.md) › Using Daf</sub>

# Sound

Some books want weather. When a storm hits in a story I'd like to hear the rain, and when the characters sit down by a fire I'd like the fire to crackle somewhere behind the page. Sound does that: a quiet bed of recorded sound under the book that changes when the scene does, so a chapter that moves from a ship's deck to a crowded inn moves from the sea to the murmur of a room.

It works two ways: while I read in Daf, and while I read on the Kindle with a phone, a tablet or the computer playing beside it.

## In Daf's reader

The **wave button** in the book's top bar (**Sound** in the round menu on a phone) turns it on. The first time in a new part of a book there's a short wait while Daf reads that stretch, about twenty seconds, and then the sound fades in. The same button shows what the scene is, **On the shore by the pyre, the village by the sea**, with the **Volume** and **Turn off Sound**.

From then on it follows the page. When I turn into a new scene, the old sounds fade out over a few seconds and the new ones fade in, so nothing jumps. Daf reads the next part of the book while I'm halfway through this one, so after the first wait the sound is usually there already.

It stays on for books on that device until I turn it off, and it stops when I close the book.

## Beside the Kindle

On the Kindle, **Daf › Sound in Daf** in KOReader's menu turns on sending the page. A few seconds after each page turn, while the Kindle has Wi-Fi, the plugin sends the words on that page and how far into the book it is, and Daf finds the place the same way it finds my place for the audiobook.

Then on Today, on whatever is going to play the sound, a **Sound** row shows up with the Kindle's book (it's there for half an hour after the last page came in). **Sound** starts it and **Stop** stops it, and the row shows the scene and a volume slider while it plays. It changes scenes as I turn pages on the Kindle, without me touching the phone.

For now the page has to stay open with the screen on, so a computer or a tablet on a stand works best.

## How it chooses the sounds

The model reads each part of the book once, a chapter or half of a long one, and splits it into scenes by where they take place and what you'd hear there. Each scene gets up to three sounds and how loud each should be. It's told to keep it gentle, to start a new scene only when the place or the weather really changes, and to leave single events alone: a door or a gunshot isn't a scene. A scene where nothing fits gets silence.

For books without places, like essays, prayer or a book of daily readings, it can use the quiet music instead, or nothing at all.

What it decided is kept for the book, so it's only read once. If the book's file changes, it reads it again.

## The sounds

There are a hundred and thirty-four now, all recordings that loop without a seam. Each kind is set to the same loudness as the others like it, so going from the rain on a tent to the inside of a train doesn't make me jump:

- **Rain and storms:** steady rain, drizzle, a downpour, a thunderstorm and a summer night with thunder far off, and rain the way you hear it from somewhere: on a tent, a window, a tin roof, the roof from the attic, a car, an umbrella, a city street and a wood, running down a gutter, the drips after it stops, and a storm in the trees or on a tent.
- **Wind, snow and sand:** a gale round the house, a thin empty wind, wind in the trees, in dry grass and in the reeds, on a mountain, across a desert and over polar ice, a sandstorm, snow falling at night, a cold autumn wood, and a barn creaking in the wind.
- **Fire:** a hearth, a campfire, a wood stove, and a fire in a big hall that rings.
- **Water:** surf, a rough sea, ocean breakers, a stream, a wide river, a waterfall, a lake, a pebble beach, a canal in the morning, a fountain in a courtyard, a watermill, a cave, a sea cave, and under the water.
- **Ships:** a wooden ship creaking, an engine room below decks, a sailboat's cabin, a rowing boat, a harbour, gulls on a rocky shore, a river boat, and the rigging of moored boats in the wind.
- **Getting around:** a train, an old steam train, a big station, the underground, a tram, a bus, a car, an airliner, a horse-drawn carriage, and a spaceship.
- **Outdoors:** a forest at dawn, a spring garden, a meadow, a rainforest and a jungle by day, crickets on a warm night, frogs, a pond at night, an owl, wolves, loons, cicadas at noon, a hot afternoon in a field, a beehive, crows in fog, an evening in the country, a summer night by a farm, a farm by day, sheep with their bells, and cows with theirs.
- **Towns and people:** a busy crowd indoors, a café or an inn, chatter on a street, a city at night and by day, a road with birds, a market, an old-city bazaar, a fairground, a pub, a big crowd, a party in the next room, a museum, and fireworks far off.
- **Rooms:** church bells, a cathedral, a hall before prayers, a library, a clock ticking, a quiet flat at night, a big hall of quiet people, a hospital, a hotel lobby, a prison, a pan frying, an electric fan, a pencil on paper, and a tunnel.
- **Work:** a factory, a forge, a printing works, a workshop, a typewriter, and a hall humming with machines.
- **Music**, for when no place can be heard: calm, vast, sacred, meditative, a bowl and a gong, piano, a sad cello, guitar, harp, a choir with no words, two drones, something darker for dread, and a church organ.

Thirty of them are the recordings [Chataltul](https://stuffs.tiresia.xyz/kavana/) plays (its [list of sounds](https://github.com/franz-rosenzweig/kavana/blob/master/docs/sounds.md) names who recorded each one), and Daf fetches its own copy of one the first time it's needed. The rest are Daf's own. I found them on Freesound, and they're all Creative Commons 0 too, which means the people who recorded them gave them away to everyone. Nobody has to credit them for that, but I want to, so [The sounds and who recorded them](sound-list.md) names every one.

## Good to know

- A book needs to be an EPUB for Sound, since Daf reads its text to find the scenes.
- Sound and Listen can play together: the voice reads the page and the scene plays underneath.
- On the Kindle, sending the page uses a little Wi-Fi with each page turn, so I leave **Sound in Daf** off when I'm not using it.
- Daf's own sounds live on the server it runs on. A new copy of Daf has only the thirty from Chataltul until `tools/sounds.py make` has made the rest (the [working notes](OPERATIONS.md) say how), and until then Sound just chooses from the ones it has.
