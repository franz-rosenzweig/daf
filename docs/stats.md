<sub>[Daf docs](README.md) › Using Daf</sub>

# Stats

**Stats** is the page that looks back: how many days in a row, how much this week and this month, when in the day you actually read, and which books you started and left. Today tells you about today, and this page tells you about the habit. Everything here is in counted minutes and in your home time zone, so it matches the ring.

![The Stats page](images/stats.png)
*Stats: the streak, the totals, and the charts.*

## Streak

The big number is how many days in a row you've read at all, with how many of them reached the hour and your best run so far. Under it are the last two weeks as fourteen circles: a full one is a day at the hour, a ring is a day with some reading, and an empty one is a day with none. I find the rings more encouraging than the number, because a ring still counts.

## Totals

Today, the last 7 days, the last 30 days (with the average a day), and Year 30 so far, with how many days reached the hour. Under the totals is the projection: at the last month's pace, how many hours Year 30 ends with, next to the 365 that an hour every day would make. It's honest, which is the point.

## When you read

Two charts over the last 90 days. The first is the hour of the day you start reading, which showed me that most of my reading happens after nine at night. The second is the average minutes for each day of the week, with today's weekday darker.

## Where the minutes came from

The last 90 days by source, the Kindle, Books in Daf, Manga in Daf, Audiobooks, Articles in Daf and Paper, and under it the highlights you made each week for the last twelve weeks.

## Waiting for you

This is my favorite card. It lists the books you started and then left for two weeks or more, somewhere between the first pages and the end, with how far you got and when you last read. As the card says, one sitting might be all it takes. Click one to open its page, and from there **Read in Daf** or **Put on the nightstand**.

## Reading now, On this day, Finished

- **Reading now:** the books you're partway through and read in the last two weeks, with their progress.
- **On this day:** highlights you made on this date in earlier years, which open at their spot.
- **Finished:** the books you read to the end on the Kindle in the last two years, as covers.

## From the command line

On the server, `daf today` prints today's minutes by source and sitting, and `daf year` prints Year 30 so far (`daf year 29` for the year before). Both take `--json`, which is how my dashboard shows a Reading card without opening Daf.

If the numbers here ever disagree with Today, look at [Where the minutes come from](reading-time.md): it's almost always a switch in **What counts toward the goal**.

<sub>Next: [Manga](manga.md) →</sub>
