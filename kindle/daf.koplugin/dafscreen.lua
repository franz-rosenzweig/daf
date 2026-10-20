--[[
The Daf tab: today's minutes, the day's review with Keep and Less often, the nightstand, and
when Daf last answered, with Refresh. Drawn with canvas.lua like Home and the shelves, the bar
at the bottom with Daf lit. Opened from the bar, from Home's today, Tools → Daf → Open Daf, a
gesture ("Daf: open the Daf screen"), and the first wake of the morning when that's on.

Works offline from the last answer Daf gave; Keep/Less taps made offline are queued and sent
when Wi-Fi is back. Swipe left and right on the highlight to go through the review.
]]
local _ = require("gettext")
local Canvas = require("canvas")
local C = Canvas.C
local px, SERIF, SANS, MID, SOFT, WHITE, BLACK = C.px, C.SERIF, C.SANS, C.MID, C.SOFT, C.WHITE, C.BLACK

local DONE_LABEL = { keep = _("Kept"), less = _("Less often"), later = _("Tomorrow") }

local DafScreen = Canvas:extend{
    name = "daf_screen",
}

function DafScreen:init()
    self.idx = self:firstOpen()
    Canvas.init(self)
end

function DafScreen:items()
    if not self.daf:homeIsToday() then return {} end
    return self.daf:home().review or {}
end

function DafScreen:firstOpen()
    for i, it in ipairs(self:items()) do
        if not it.action then return i end
    end
    return 1
end

function DafScreen:layout()
    self.ops, self.taps = {}, {}
    local W = self.dimen.w
    local L, R = px(56), W - px(56)
    local inner = R - L
    local daf = self.daf
    local home = daf:home()
    local y = self:statusLine()
    local nav_top = self:navBar("daf")

    -- today
    y = y + px(30)
    local s = daf:summary()
    local goal = daf:goal()
    local total = math.floor(s.total)
    self:text(_("TODAY"), SANS, 21, L, y, { bold = true })
    y = y + px(34)
    local nw = self:text(tostring(total), SERIF, 76, L, y - px(8), { bold = true })
    local line = total >= goal and _("That's the goal.") or string.format(_("%d to go"), goal - total)
    self:text(string.format(_("of %d minutes today · %s"), goal, line), SERIF, 34, L + nw + px(18), y + px(40), { max_w = inner - nw - px(18) })
    y = y + px(112)
    self:bar(L, y, inner, px(16), total / goal)
    y = y + px(32)
    local parts = { string.format(_("Kindle %d min"), math.floor(s.kindle)) }
    if s.other >= 1 then table.insert(parts, string.format(_("elsewhere %d"), math.floor(s.other))) end
    if daf:homeIsToday() and (tonumber(home.streak_any) or 0) > 1 then
        if (tonumber(home.streak_goal) or 0) > 1 then
            table.insert(parts, string.format(_("%d days in a row at the goal"), home.streak_goal))
        else
            table.insert(parts, string.format(_("%d days in a row"), home.streak_any))
        end
    end
    local main = daf:mainLine()
    if main then table.insert(parts, 1, main) end
    if s.year_day then table.insert(parts, string.format(_("Year 30, day %d, %s h so far"), s.year_day, tostring(s.year_hours or 0))) end
    self:box(table.concat(parts, " · "), SANS, 24, L, y, inner, 2, { color = MID })
    y = y + px(84)
    self:rect(L, y, inner, px(2))

    -- from the bottom up: when Daf answered, with Refresh; the nightstand
    local foot_h = px(64)
    local foot_y = nav_top - foot_h - px(22)
    local offset = tonumber(daf.settings:readSetting("tz_offset")) or -25200
    local fetched = home.fetched and os.date("!%H:%M", home.fetched + offset)
    local pending = daf:pendingCount()
    self:text((fetched and string.format(_("From Daf at %s"), fetched) or _("Not synced yet"))
              .. (pending > 0 and string.format(_(" · %d to send"), pending) or ""),
              SANS, 23, L, foot_y + px(18), { color = MID })
    local rw = px(200)
    self:pill(R - rw, foot_y, rw, foot_h, false)
    self:text(_("Refresh"), SANS, 25, R - math.floor(rw / 2), foot_y + px(16), { align = "center", bold = true })
    self:tap(R - rw, foot_y - px(10), rw, foot_h + px(20), function() daf:refreshHome(self, true) end)

    local stand = home.nightstand or {}
    local row_h = px(74)
    local n = math.min(3, #stand)
    local stand_top = foot_y - px(30) - px(44) - math.max(1, n) * row_h
    self:rect(L, stand_top - px(20), inner, px(1), SOFT)
    self:text(home.nightstand_chosen and _("NIGHTSTAND") or _("LATELY ON THE KINDLE"), SANS, 21, L, stand_top, { bold = true })
    local ry = stand_top + px(44)
    if n == 0 then
        self:box(_("Nothing on the nightstand yet. Pick up to three books in Daf."), SERIF, 26, L, ry + px(10), inner, 2, { color = MID })
    end
    for i = 1, n do
        local b = stand[i]
        local page, pages = daf:localProgress(b.md5s or {})
        page, pages = page or b.page, pages or b.total
        local frac = (page and pages and pages > 0) and page / pages or nil
        local where = frac and string.format(_("p. %d of %d"), page, pages) or _("not started here")
        local ww = self:measure(where, SANS, 23)
        self:text(C.shortTitle(b.title), SERIF, 30, L, ry + px(12), { bold = true, max_w = inner - ww - px(190) })
        self:text(where, SANS, 23, R - px(150), ry + px(18), { align = "right", color = MID })
        self:bar(R - px(130), ry + px(26), px(130), px(12), frac or 0)
        if i < n then self:rect(L, ry + row_h - px(1), inner, px(1), SOFT) end
        self:tap(L, ry, inner, row_h, function() daf:openBook(b, self) end)
        ry = ry + row_h
    end

    -- the review, in what's left
    y = y + px(26)
    local items = self:items()
    local done = 0
    for _i, it in ipairs(items) do if it.action then done = done + 1 end end
    self:text(_("REVIEW"), SANS, 21, L, y, { bold = true })
    if #items > 0 then
        self:text(string.format(_("%d of %d done"), done, #items), SANS, 22, R, y - px(1), { align = "right", color = MID })
    end
    local top = y
    y = y + px(44)
    local bh = px(70)
    local by = stand_top - px(20) - px(30) - bh
    local it = items[self.idx]
    if it then
        local meta = C.shortTitle(it.title)
        if it.author and it.author ~= "" then meta = meta .. " · " .. it.author end
        if it.page then meta = meta .. " · " .. string.format(_("p. %d"), it.page) end
        if it.action then meta = meta .. "  —  " .. (DONE_LABEL[it.action] or it.action) end
        local meta_y = by - px(24) - px(32)
        self:text(meta, SANS, 23, L, meta_y, { color = MID, max_w = inner })
        local room = meta_y - px(20) - y
        local text = "“" .. (it.text or "") .. "”"
        local note = it.note and it.note ~= "" and it.note or nil
        -- the biggest type it fits in, down to 30
        local size = 30
        for _i, sz in ipairs({ 44, 38, 34 }) do
            if self:textHeight(text, SERIF, sz, inner) + (note and px(90) or 0) <= room then size = sz; break end
        end
        local lh = self:lineHeight(SERIF, size, inner)
        local used = self:box(text, SERIF, size, L, y, inner, math.max(1, math.floor((room - (note and lh or 0)) / lh)))
        if note then
            local nl = self:lineHeight(SANS, 25, inner)
            local left = math.floor((room - used - px(14)) / nl)
            if left > 0 then self:box(_("Your note: ") .. note, SANS, 25, L, y + used + px(14), inner, left) end
        end
        local small = px(110)
        local mid = math.floor((inner - 2 * small - 4 * px(16)) / 2)
        local x0 = L
        self:pill(x0, by, small, bh, false); self:text("‹", SANS, 38, x0 + math.floor(small / 2), by + px(10), { align = "center", bold = true, color = self.idx > 1 and BLACK or SOFT })
        self:tap(x0, by, small, bh, function() self:move(-1) end)
        x0 = x0 + small + px(16)
        self:pill(x0, by, mid, bh, false); self:text(_("Less often"), SANS, 27, x0 + math.floor(mid / 2), by + px(17), { align = "center" })
        self:tap(x0, by, mid, bh, function() self:act("less") end)
        x0 = x0 + mid + px(32)
        self:pill(x0, by, mid, bh, true); self:text(_("Keep"), SANS, 27, x0 + math.floor(mid / 2), by + px(17), { align = "center", bold = true, color = WHITE })
        self:tap(x0, by, mid, bh, function() self:act("keep") end)
        x0 = R - small
        self:pill(x0, by, small, bh, false); self:text("›", SANS, 38, x0 + math.floor(small / 2), by + px(10), { align = "center", bold = true, color = self.idx < #items and BLACK or SOFT })
        self:tap(x0, by, small, bh, function() self:move(1) end)
    else
        local msg = daf:homeIsToday() and _("No highlights to review today.")
            or _("Today's review arrives the next time the Kindle is on Wi-Fi. Tap Refresh to fetch it now.")
        self:box(msg, SERIF, 30, L, y + px(60), inner, 3, { align = "center", color = MID })
    end
    self.review_area = { y = top, h = by + bh - top }
end

function DafScreen:onPageSwipe(ges)
    local a = self.review_area
    local y = ges.pos.y - self.dimen.y
    if a and y >= a.y and y <= a.y + a.h then
        if ges.direction == "west" then self:move(1) end
        if ges.direction == "east" then self:move(-1) end
    end
    return true
end

function DafScreen:act(action)
    local items = self:items()
    local it = items[self.idx]
    if not it then return end
    it.action = action
    self.daf:queueReview(it.id, action)
    for i = self.idx + 1, #items do
        if not items[i].action then self.idx = i; break end
    end
    self:update()
end

function DafScreen:move(d)
    local i = self.idx + d
    if i >= 1 and i <= #self:items() then self.idx = i; self:update() end
end

-- Back goes Home, as from a shelf.
function DafScreen:onClose()
    self:goHomeScreen()
    return true
end

return DafScreen
