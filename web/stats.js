/* Daf stats: streaks, totals and the Year 30 projection, when you read, books in progress and
   stalled, highlights per week, and highlights from this day in other years. */
(() => {
const C = window.DafCore, { api, esc, $, epochDate, shortTitle, cover, bar } = C;
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const hm = m => { m = Math.round(m || 0); return m >= 60 ? Math.floor(m / 60) + ' h ' + (m % 60 ? m % 60 + ' min' : '') : m + ' min'; };
const bars = (vals, labels, unit, hi) => {
  const max = Math.max(1, ...vals);
  return '<div class="sbars">' + vals.map((v, i) => '<div class="sb' + (hi === i ? ' hi' : '') + '" title="' + esc(labels[i]) + ': ' + v + ' ' + unit + '"><i style="height:' + Math.max(v ? 3 : 0, Math.round(v / max * 100)) + '%"></i><span>' + esc(labels[i]) + '</span></div>').join('') + '</div>';
};
function bookLine(b, extra){
  return '<a class="brow" href="#' + (b.readable ? 'ebook/' : 'book/') + encodeURIComponent(b.id) + '">' + cover(b, 'cv sm') + '<span class="bt"><b>' + esc(shortTitle(b.title)) + '</b><span class="mute tiny">' + esc(b.author || '') + '</span>' +
    '<span class="tiny mute">' + bar(b.progress) + ' ' + Math.round(b.progress) + '% · ' + (extra || '') + '</span></span></a>';
}

C.views.stats = async () => {
  $('#main').innerHTML = '<div class="top"><h1>Stats</h1><span class="spacer"></span><span class="mute tiny">Counted minutes, your home time zone</span></div><div class="page" id="statspage"><span class="mute">Loading…</span></div>';
  const s = await C.swr('/api/stats');
  const t = s.totals, k = s.streak, goal = s.goal || 60, at = goal === 60 ? 'at the hour' : 'at your goal';
  let h = '<div class="sgrid">';
  const lead = k.goal > 0 ? [k.goal, 'in a row ' + at, k.any + ' day' + (k.any === 1 ? '' : 's') + ' in a row with some reading'] : [k.any, 'in a row reading', 'None ' + at + ' yet in this streak'];
  h += '<section class="card"><h2>Streak</h2><div class="sbig"><b>' + lead[0] + '</b><span>day' + (lead[0] === 1 ? '' : 's') + ' ' + lead[1] + '</span></div>' +
    '<div class="mute">' + lead[2] + ' · best: ' + k.best_goal + ' ' + at + ', ' + k.best_any + ' reading</div>' +
    '<div class="dots">' + s.days14.map(d => '<span class="dot2' + (d.minutes >= goal ? ' full' : d.minutes >= 1 ? ' some' : '') + '" title="' + d.date + ': ' + Math.round(d.minutes) + ' min"></span>').join('') + '</div><span class="tiny mute">The last two weeks: full = ' + (goal === 60 ? 'the hour' : 'the goal') + ', ring = some reading</span></section>';
  h += '<section class="card"><h2>Totals</h2><div class="kv">' +
    '<span>Today</span><b>' + hm(t.today) + '</b><span>Last 7 days</span><b>' + hm(t.week) + '</b><span>Last 30 days</span><b>' + hm(t.month) + ' · ' + Math.round(t.avg30) + ' min a day</b>' +
    '<span>Year 30 so far</span><b>' + t.year30_hours + ' h · ' + t.year30_days_goal + ' of ' + t.year30_elapsed + ' days ' + at + '</b></div>' +
    '<p class="sproj">At the last month’s pace, Year 30 ends with about <b>' + t.projection_hours + ' hours</b>. ' + (goal === 60 ? 'An hour every day is ' : 'Your goal every day comes to ') + t.goal_hours + '.</p></section>';
  h += '</div>';
  h += '<div class="sgrid"><section class="card"><h2>When you read</h2><span class="mute tiny">Last 90 days, by the hour you started</span>' +
    bars(s.hours, s.hours.map((_, i) => i % 3 === 0 ? (i === 0 ? '12a' : i < 12 ? i + 'a' : i === 12 ? '12p' : (i - 12) + 'p') : ''), 'min') +
    '<span class="mute tiny">Average minutes by day of the week</span>' + bars(s.weekdays, DAYS, 'min a day', new Date().getDay()) + '</section>';
  h += '<section class="card"><h2>Where the minutes came from</h2><span class="mute tiny">Last 90 days</span><div class="kv">' +
    s.sources.map(x => '<span' + (x.counted ? '' : ' class="mute"') + '>' + esc(x.label) + (x.counted ? '' : ' (not counted)') + '</span><b>' + hm(x.minutes) + '</b>').join('') + '</div>' +
    '<span class="mute tiny">Highlights per week, last 12 weeks</span>' + bars(s.highlight_weeks.map(w => w.n), s.highlight_weeks.map((w, i) => i % 2 ? '' : w.week.slice(5).replace('-', '/')), 'highlights', 11) + '</section></div>';
  if (s.stalled.length) h += '<section class="card"><div class="cardh"><h2>Waiting for you</h2><span class="mute tiny">Started, then left for two weeks or more. One sitting might be all it takes.</span></div><div class="brows">' +
    s.stalled.map(b => bookLine(b, 'last read ' + b.days_ago + ' days ago')).join('') + '</div></section>';
  if (s.in_progress.length) h += '<section class="card"><h2>Reading now</h2><div class="brows">' + s.in_progress.map(b => bookLine(b, b.days_ago ? b.days_ago + ' days ago' : 'today')).join('') + '</div></section>';
  if (s.on_this_day.length) h += '<section class="card"><h2>On this day</h2>' + s.on_this_day.map(x => '<div class="hlc"><q' + (x.open ? ' class="go" data-open="' + esc(x.open) + '" role="link" tabindex="0" title="Open at this spot"' : '') + '>' + C.HL.quote(x.text) + '</q><div class="meta tiny mute">' + esc(shortTitle(x.title)) + ' · ' + x.year + ' (' + x.years_ago + ' year' + (x.years_ago === 1 ? '' : 's') + ' ago)</div></div>').join('') + '</section>';
  if (s.finished.length) h += '<section class="card"><h2>Finished</h2><span class="mute tiny">Read to the end on the Kindle, last two years</span><div class="libgrid">' +
    s.finished.map(b => '<a class="libcard" href="#book/' + encodeURIComponent(b.id) + '">' + cover(b, 'cv lib') + '<b>' + esc(shortTitle(b.title)) + '</b><span class="mute tiny">' + epochDate(b.last_read) + '</span></a>').join('') + '</div></section>';
  $('#statspage').innerHTML = h;
};
})();
