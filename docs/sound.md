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

There are thirty, all recordings that loop without a seam, at one loudness:

- **Rain:** steady rain, drizzle, a downpour, a thunderstorm, and a summer night with thunder far off.
- **Wind:** a gale round the house, and a thin empty wind for moors and ruins.
- **Fire:** a hearth, a campfire, a wood stove, and a fire in a big hall that rings.
- **Water:** surf, a rough sea, ocean breakers, and a stream.
- **Outdoors:** a forest at dawn, a spring garden, a meadow, a rainforest, a warm night with crickets and cicadas, and just crickets.
- **People:** a busy crowd indoors, the murmur of a café or an inn, chatter on a street, and a city at night.
- **Music**, for when no place can be heard: calm, vast, sacred, meditative, and a bowl and a gong.

They're the same recordings [Chataltul](https://stuffs.tiresia.xyz/kavana/) plays, all Creative Commons 0 from Freesound (Chataltul's [list of sounds](https://github.com/franz-rosenzweig/kavana/blob/master/docs/sounds.md) names who recorded each one). Daf keeps its own copy, fetched the first time a sound is needed.

## Good to know

- A book needs to be an EPUB for Sound, since Daf reads its text to find the scenes.
- Sound and Listen can play together: the voice reads the page and the scene plays underneath.
- On the Kindle, sending the page uses a little Wi-Fi with each page turn, so I leave **Sound in Daf** off when I'm not using it.
