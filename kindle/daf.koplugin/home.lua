--[[
Home: the Kindle's front page, opened when KOReader starts, after a book closes, and from the
file browser's house icon (Tools → Daf has the switches). From the top: the time, the date with
the Hebrew date, and the battery; today's minutes toward the Daf goal, with a bar (and this Shabbat's
parasha, which opens the Torah shelf); the book in hand with Resume; the books read lately;
and the bar of Home, Shelves, History, Daf and Search. The review is on the Daf tab and the
shelves on Shelves.

Drawn with canvas.lua. Books on Daf's private list (home.private_md5s) never show here.
]]
local ReadHistory = require("readhistory")
local lfs = require("libs/libkoreader-lfs")
local _ = require("gettext")
local Canvas = require("canvas")
local C = Canvas.C
local px, SERIF, SANS, MID, SOFT, WHITE = C.px, C.SERIF, C.SANS, C.MID, C.SOFT, C.WHITE

local Home = Canvas:extend{
    name = "daf_home",
}

-- The books in KOReader's history, newest first, without private ones.
function Home:books(limit)
    local private = self:privateMd5s()
    local out = {}
    for _i, item in ipairs(ReadHistory.hist or {}) do
        local file = item.file
        if file and lfs.attributes(file, "mode") == "file" then
            local b = C.bookInfo(file)
            if not (b.md5 and private[b.md5]) then
                b.time = item.time
                table.insert(out, b)
                if #out >= limit then break end
            end
        end
    end
    return out
end

function Home:layout()
    self.ops, self.taps = {}, {}
    local W = self.dimen.w
    local L, R = px(56), W - px(56)
    local inner = R - L
    local daf = self.daf
    local home = daf:home()
    local y = self:statusLine()
    local nav_top = self:navBar("home")

    -- today (200): the minutes toward Daf's goal and a bar, with this Shabbat's parasha on the right
    local s = daf:summary()
    local goal = daf:goal()
    local total = math.floor(s.total)
    local top = y
    self:text(_("TODAY"), SANS, 21, L, y + px(30), { bold = true })
    if daf:homeIsToday() and home.parasha then
        self:text(string.format(_("Shabbat: %s ›"), home.parasha), SANS, 22, R, y + px(29), { align = "right" })
        self:tap(R - px(380), y + px(10), px(380), px(60), function() self:openFolderNamed("Torah") end)
    end
    local nw = self:text(tostring(total), SERIF, 64, L, y + px(56), { bold = true })
    self:text(string.format(_("of %d minutes"), goal), SERIF, 36, L + nw + px(16), y + px(84))
    self:bar(L, y + px(166), inner, px(16), total / goal)
    local line = total >= goal and _("That's the goal.") or string.format(_("%d to go"), goal - total)
    local lw = self:text(line, SANS, 24, L, y + px(196), { bold = true })
    if s.year_day then
        self:text(string.format(_(" · Year 30, day %d · %s hours so far"), s.year_day, tostring(s.year_hours or 0)), SANS, 24, L + lw, y + px(196), { color = MID, max_w = inner - lw })
    end
    self:tap(L, top + px(60), inner - px(400), px(190), function() daf:showScreen() end)
    self:tap(L, top + px(150), inner, px(100), function() daf:showScreen() end)
    y = y + px(250)
    self:rect(L, y, inner, px(2))

    -- lately, at the bottom: five across
    local books = self:books(6)
    local gap = px(32)
    local lw2 = math.floor((inner - 4 * gap) / 5)
    local lh2 = math.floor(lw2 * 1.5)
    local lately_top = nav_top - px(36) - (px(44) + lh2 + px(56))
    if #books > 1 then
        self:rect(L, lately_top - px(26), inner, px(1), SOFT)
        self:text(_("LATELY"), SANS, 21, L, lately_top, { bold = true })
        self:text(_("History ›"), SANS, 22, R, lately_top - px(1), { align = "right" })
        self:tap(R - px(200), lately_top - px(14), px(200), px(56), function() self:history() end)
        local ly = lately_top + px(44)
        for i = 2, #books do
            local b = books[i]
            local x = L + (i - 2) * (lw2 + gap)
            self:coverOrTitle(b, x, ly, lw2, lh2)
            self:bar(x, ly + lh2 + px(12), lw2, px(10), b.pct or 0)
            self:text(string.format("%d%%", math.floor((b.pct or 0) * 100 + 0.5)), SANS, 20, x, ly + lh2 + px(28), { color = MID })
            self:tap(x, ly, lw2, lh2 + px(56), function() self:openBook(b.file) end)
        end
    else
        lately_top = nav_top
    end

    -- the book in hand, in the middle
    local cur = books[1]
    local band_top, band_bottom = y + px(40), lately_top - px(26) - px(40)
    if not cur then
        self:box(_("Nothing read on this Kindle yet. Open a book from Shelves."), SERIF, 32, L, band_top + px(60), inner, 3, { align = "center", color = MID })
        return
    end
    local ch = math.min(px(600), band_bottom - band_top)
    local cw = math.floor(ch / 1.5)
    y = band_top + math.floor((band_bottom - band_top - ch) / 2)
    self:coverOrTitle(cur, L, y, cw, ch)
    local x2 = L + cw + px(48)
    local w2 = R - x2
    local bh = px(84)
    local by = y + ch - bh - px(24) - px(32) - px(30)        -- the progress bar
    self:text(_("CONTINUE READING"), SANS, 22, x2, y + px(4), { bold = true })
    -- title, subtitle and author share what's above the bar; the subtitle gives way first
    local author_h = cur.author and self:lineHeight(SANS, 30, w2) or 0
    local room = by - px(20) - (y + px(44)) - (author_h > 0 and author_h + px(8) or 0)
    local tl = self:lineHeight(SERIF, 60, w2)
    local th = self:box(C.shortTitle(cur.title), SERIF, 60, x2, y + px(44), w2, math.max(1, math.min(3, math.floor(room / tl))), { bold = true })
    local yy = y + px(44) + th + px(6)
    local sub = C.subtitle(cur.title)
    if sub then
        local sl = self:lineHeight(SERIF, 27, w2)
        local n = math.min(3, math.floor((room - th - px(6)) / sl))
        if n > 0 then yy = yy + self:box(sub, SERIF, 27, x2, yy, w2, n, { color = MID }) + px(8) end
    end
    if cur.author then self:text(cur.author, SANS, 30, x2, yy, { max_w = w2 }) end
    self:bar(x2, by, w2, px(16), cur.pct or 0)
    self:text(string.format("%d%%", math.floor((cur.pct or 0) * 100 + 0.5)), SANS, 24, x2, by + px(26))
    local ago = math.floor((os.time() - (cur.time or os.time())) / 86400)
    self:text(ago <= 0 and _("last read today") or ago == 1 and _("last read yesterday") or string.format(_("last read %d days ago"), ago),
              SANS, 24, R, by + px(26), { align = "right", color = MID })
    local bw = px(260)
    self:pill(x2, y + ch - bh, bw, bh, true)
    self:text(_("Resume  ›"), SANS, 31, x2 + math.floor(bw / 2), y + ch - bh + px(21), { align = "center", bold = true, color = WHITE })
    self:tap(L, y, inner, ch, function() self:openBook(cur.file) end)
end

function Home:goHomeScreen() end           -- already here

function Home:openFolderNamed(name)
    for _i, sh in ipairs(C.folders(C.homeDir())) do
        if sh.name == name then return self:openShelf(sh.path) end
    end
end

return Home
