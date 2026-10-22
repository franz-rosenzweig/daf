--[[
What Home (home.lua) and a shelf (shelf.lua) share: a full screen that draws itself at fixed
places, designed at the Paperwhite's 1236 px wide and scaled to the screen, with a list of tap
areas; the type (Literata and Atkinson Hyperlegible, with Noto in reserve); the status line and
the bar of Home, Shelves, History, Daf and Search; book covers (covers.lua says where they come
from); and what a book's notes file says about it.

Night mode inverts it like the rest of KOReader: covers keep their look (ImageWidget's
original_in_nightmode), the shelf drawings and icons turn white on black.
]]
local Blitbuffer = require("ffi/blitbuffer")
local Covers = require("covers")
local Device = require("device")
local DocSettings = require("docsettings")
local Font = require("ui/font")
local Geom = require("ui/geometry")
local GestureRange = require("ui/gesturerange")
local ImageWidget = require("ui/widget/imagewidget")
local InputContainer = require("ui/widget/container/inputcontainer")
local TextBoxWidget = require("ui/widget/textboxwidget")
local TextWidget = require("ui/widget/textwidget")
local UIManager = require("ui/uimanager")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")
local _ = require("gettext")
local Screen = Device.screen

local C = {}
C.BLACK, C.WHITE = Blitbuffer.COLOR_BLACK, Blitbuffer.COLOR_WHITE
C.MID, C.SOFT = Blitbuffer.COLOR_GRAY_5, Blitbuffer.COLOR_GRAY_B
C.SERIF = { "Literata-Regular.ttf", "NotoSerif-Regular.ttf" }
C.SANS = { "AtkinsonHyperlegibleNext-Regular.ttf", "NotoSans-Regular.ttf" }
C.BOOK_EXT = { epub = true, pdf = true, mobi = true, azw3 = true, azw = true, fb2 = true, cbz = true, cbr = true, djvu = true, txt = true, docx = true }
C.PLUGIN_DIR = (debug.getinfo(1, "S").source:match("^@(.*/)[^/]*$")) or "./"
local BLACK, WHITE, MID, SOFT, SERIF, SANS = C.BLACK, C.WHITE, C.MID, C.SOFT, C.SERIF, C.SANS

local Canvas = InputContainer:extend{
    daf = nil,
    covers_fullscreen = true,
    active_tab = nil,
}
Canvas.C = C

-- ---------------------------------------------------------------- sizes and type

local K = 1
function C.px(v) return math.floor(v * K + 0.5) end
local px = C.px

local faces = {}
function C.face(list, size)
    local key = list[1] .. size
    if faces[key] then return faces[key] end
    local unit = Screen:scaleBySize(1000) / 1000      -- Font:getFace scales sizes by the screen
    for _i, name in ipairs(list) do
        local ok, f = pcall(Font.getFace, Font, name, px(size) / unit)
        if ok and f then faces[key] = f; return f end
    end
    faces[key] = Font:getFace("cfont", px(size) / unit)
    return faces[key]
end
local face = C.face

-- "Walden: Or, Life in the Woods" → "Walden"; also cuts at " — " and "(".
function C.shortTitle(t)
    t = t or ""
    -- (dashes are several bytes: matched as whole strings, not in a [set])
    local s = t:gsub("%s+—%s.*$", ""):gsub("%s+–%s.*$", ""):gsub("%s+%-%-%s.*$", ""):gsub("%s*[:%(].*$", "")
    return s ~= "" and s or t
end

function C.subtitle(t)
    return (t or ""):match("^[^:]+:%s*(.+)$")
end

-- ---------------------------------------------------------------- books and folders

function C.bookCount(dir, depth)
    depth = depth or 0
    local n = 0
    local ok, iter, obj = pcall(lfs.dir, dir)
    if not ok then return 0 end
    for f in iter, obj do
        if f:sub(1, 1) ~= "." then
            local p = dir .. "/" .. f
            local mode = lfs.attributes(p, "mode")
            if mode == "directory" and depth < 6 and not f:match("%.sdr$") then
                n = n + C.bookCount(p, depth + 1)
            elseif mode == "file" and C.BOOK_EXT[(f:match("%.([^.]+)$") or ""):lower()] then
                n = n + 1
            end
        end
    end
    return n
end

-- Every book under dir, six folders deep.
function C.allBooks(dir, out, depth)
    out, depth = out or {}, depth or 0
    local ok, iter, obj = pcall(lfs.dir, dir)
    if not ok then return out end
    for f in iter, obj do
        if f:sub(1, 1) ~= "." then
            local p = dir .. "/" .. f
            local mode = lfs.attributes(p, "mode")
            if mode == "directory" and depth < 6 and not f:match("%.sdr$") then
                C.allBooks(p, out, depth + 1)
            elseif mode == "file" and C.BOOK_EXT[(f:match("%.([^.]+)$") or ""):lower()] then
                table.insert(out, p)
            end
        end
    end
    return out
end

function C.folderIcon(path)
    for _i, c in ipairs({ ".cover.png", ".cover.jpg", "cover.png", "cover.jpg" }) do
        if lfs.attributes(path .. "/" .. c, "mode") == "file" then return path .. "/" .. c end
    end
end

-- The folders in dir, Nightstand first: {name, path, icon, n}.
function C.folders(dir)
    local out = {}
    local ok, iter, obj = pcall(lfs.dir, dir or "/")
    if not ok then return out end
    for f in iter, obj do
        local p = dir .. "/" .. f
        if f:sub(1, 1) ~= "." and lfs.attributes(p, "mode") == "directory" and not f:match("%.sdr$") then
            table.insert(out, { name = f, path = p, icon = C.folderIcon(p), n = C.bookCount(p, 0), folder = true })
        end
    end
    table.sort(out, function(a, b)
        if (a.name == "Nightstand") ~= (b.name == "Nightstand") then return a.name == "Nightstand" end
        return a.name:lower() < b.name:lower()
    end)
    return out
end

function C.homeDir()
    return G_reader_settings:readSetting("home_dir") or Device.home_dir or "/"
end

-- Every folder under the home folder (three deep), for moving something into: {name, path, depth}.
-- Leaves out `skip` and what's inside it.
function C.allFolders(skip)
    local out = {}
    local function walk(dir, depth)
        for _i, f in ipairs(C.folders(dir)) do
            if not (skip and (f.path == skip or f.path:sub(1, #skip + 1) == skip .. "/")) then
                table.insert(out, { name = f.name, path = f.path, depth = depth })
                if depth < 3 then walk(f.path, depth + 1) end
            end
        end
    end
    walk(C.homeDir(), 1)
    return out
end

-- ---------------------------------------------------------------- when files change

-- KOReader's own file actions (the dialog a long-press opens on a shelf: Cut, Paste, Rename,
-- Delete, a book's status…) end by refreshing the file browser under the shelf. When one was
-- started from here (C.expecting), the screens that are up refresh too. Select goes to the file
-- browser itself, where choosing several books is.
local shown = setmetatable({}, { __mode = "k" })
C.quiet = 0

-- Covers opened in the background came in: the screens waiting for them draw them.
Covers.on_ready = function(keys)
    for w in pairs(shown) do
        if UIManager:isWidgetShown(w) and w.coverReady then w:coverReady(keys) end
    end
end

local function refreshShown()
    C.expecting = nil
    for w in pairs(shown) do
        if UIManager:isWidgetShown(w) then
            if w.load then pcall(w.load, w) end
            w:update()
        end
    end
end

function C.watchFiles()
    if C.watching then return end
    C.watching = true
    local FileChooser = require("ui/widget/filechooser")
    local refreshPath = FileChooser.refreshPath
    FileChooser.refreshPath = function(fc, ...)
        local r = refreshPath(fc, ...)
        if C.expecting and C.quiet == 0 and next(shown) then
            UIManager:unschedule(refreshShown)
            UIManager:scheduleIn(0.2, refreshShown)
        end
        return r
    end
    local FileManager = require("apps/filemanager/filemanager")
    -- Cut and Copy: the shelves show where to put it
    for _i, name in ipairs({ "cutFile", "copyFile" }) do
        local orig = FileManager[name]
        FileManager[name] = function(fm, ...)
            local r = orig(fm, ...)
            if next(shown) then
                C.expecting = true
                UIManager:unschedule(refreshShown)
                UIManager:scheduleIn(0.2, refreshShown)
            end
            return r
        end
    end
    local toggle = FileManager.onToggleSelectMode
    FileManager.onToggleSelectMode = function(fm, ...)
        local r = toggle(fm, ...)
        if fm.selected_files then
            for w in pairs(shown) do
                if UIManager:isWidgetShown(w) then UIManager:close(w) end
            end
        end
        return r
    end
end

-- What the file name says, for a book never opened: "Title, The - Author (123).epub".
local function fromName(file)
    local name = file:match("([^/]+)$"):gsub("%.[^.]+$", ""):gsub("%s*%(%d+%)$", "")
    local title, author = name:match("^(.-)%s+%-%s+(.+)$")
    title = title or name
    local main, art = title:match("^(.-),%s*(The)$")
    if not main then main, art = title:match("^(.-),%s*(A)$") end
    if not main then main, art = title:match("^(.-),%s*(An)$") end
    if main then title = art .. " " .. main end
    title = title:gsub("_", ":")
    return title, author
end

-- A book, from its notes file when it has one: {file, key, title, author, md5, pct, finished, mtime,
-- read}. key is the file's partial md5 now (covers go by it); md5, the one in its notes.
function C.bookInfo(file)
    local b = { file = file, key = Covers.key(file), mtime = lfs.attributes(file, "modification") or 0 }
    local sidecar = DocSettings:findSidecarFile(file)
    if sidecar then
        local ok, ds = pcall(DocSettings.openSettingsFile, sidecar)
        local d = ok and ds and ds.data or {}
        local props = d.doc_props or {}
        b.title = props.title ~= "" and props.title or nil
        b.author = props.authors and props.authors ~= "" and props.authors:gsub("\n", ", ") or nil
        b.md5 = d.partial_md5_checksum
        b.pct = tonumber(d.percent_finished)
        b.finished = (d.summary and d.summary.status == "complete") or (b.pct and b.pct >= 0.995) or false
        b.read = lfs.attributes(sidecar, "modification")
    end
    if not b.title then
        local t, a = fromName(file)
        b.title, b.author = t, b.author or a
    end
    return b
end

-- The book's cover at w × h (a file), or nil and why: "later" (make is false: only what's kept),
-- "pending" (being opened in the background) or "none". See covers.lua.
function C.cover(book, w, h, make)
    return Covers.get(book, w, h, make == false)
end

-- Is a book on Daf's private list? It never shows a cover.
function C.isPrivate(b, set)
    return (b.md5 and set[b.md5]) or (b.key and set[b.key]) or false
end

-- The file browser's menu with everything in it. Project: Title lays the browser out again after
-- the plugins have put their items in KOReader's menu, and leaves a second, empty menu as fm.menu;
-- the first one is still in the browser, and it's the one the browser itself opens. The empty one
-- is given the same list, so whatever opens it gets everything too.
function C.fileMenu(fm)
    if not fm then return nil end
    local best = fm.menu
    for _i, w in ipairs(fm) do
        if type(w) == "table" and w.registered_widgets and w.onSwipeShowMenu
           and #w.registered_widgets > #((best and best.registered_widgets) or {}) then
            best = w
        end
    end
    if fm.menu and best and fm.menu ~= best and #(fm.menu.registered_widgets or {}) == 0
       and not fm.menu.tab_item_table then
        fm.menu.registered_widgets = best.registered_widgets
    end
    return best
end

function Canvas:privateMd5s()
    local set = {}
    for _i, m in ipairs(self.daf:home().private_md5s or {}) do set[m] = true end
    Covers.private = set
    return set
end

-- ---------------------------------------------------------------- the screen

function Canvas:init()
    self.dimen = Geom:new{ x = 0, y = 0, w = Screen:getWidth(), h = Screen:getHeight() }
    K = self.dimen.w / 1236
    faces = {}
    if Device:hasKeys() then
        self.key_events.Close = { { Device.input.group.Back } }
    end
    if Device:isTouchDevice() then
        self.ges_events.Tap = { GestureRange:new{ ges = "tap", range = function() return self.dimen end } }
        self.ges_events.Hold = { GestureRange:new{ ges = "hold", range = function() return self.dimen end } }
        self.ges_events.Swipe = { GestureRange:new{ ges = "swipe", range = function() return self.dimen end } }
    end
    self:layout()
end

function Canvas:put(fn) table.insert(self.ops, fn) end
function Canvas:tap(x, y, w, h, cb, hold) table.insert(self.taps, { x = x, y = y, w = w, h = h, cb = cb, hold = hold }) end

function Canvas:text(str, list, size, x, y, o)
    o = o or {}
    local tw = TextWidget:new{ text = str or "", face = face(list, size), bold = o.bold, fgcolor = o.color or BLACK, max_width = o.max_w }
    local w = tw:getSize().w
    local at = o.align == "right" and x - w or o.align == "center" and x - math.floor(w / 2) or x
    self:put(function(bb, ox, oy) tw:paintTo(bb, ox + at, oy + y) end)
    return w, tw:getSize().h
end

function Canvas:measure(str, list, size, bold)
    local tw = TextWidget:new{ text = str or "", face = face(list, size), bold = bold }
    local w = tw:getSize().w
    tw:free()
    return w
end

-- Text in a box w wide, at most `lines` lines (an ellipsis when it's longer). Returns the height used.
function Canvas:box(str, list, size, x, y, w, lines, o)
    o = o or {}
    local args = { text = str or "", face = face(list, size), width = w, alignment = o.align or "left", bold = o.bold, fgcolor = o.color or BLACK }
    local probe = TextBoxWidget:new{ text = "M", face = args.face, width = w }
    local line_h = probe:getSize().h
    probe:free()
    if lines < 1 then return 0, line_h end
    local tb = TextBoxWidget:new(args)
    if tb:getSize().h > line_h * lines then
        tb:free()
        args.height, args.height_overflow_show_ellipsis = line_h * lines, true
        tb = TextBoxWidget:new(args)
    end
    self:put(function(bb, ox, oy) tb:paintTo(bb, ox + x, oy + y) end)
    return tb:getSize().h, line_h
end

-- How tall str is set in a box w wide.
function Canvas:textHeight(str, list, size, w)
    local tb = TextBoxWidget:new{ text = str or "", face = face(list, size), width = w }
    local h = tb:getSize().h
    tb:free()
    return h
end

function Canvas:lineHeight(list, size, w)
    local probe = TextBoxWidget:new{ text = "M", face = face(list, size), width = w or px(400) }
    local h = probe:getSize().h
    probe:free()
    return h
end

function Canvas:rect(x, y, w, h, c)
    self:put(function(bb, ox, oy) bb:paintRect(ox + x, oy + y, w, h, c or BLACK) end)
end

function Canvas:frame(x, y, w, h, bw, r)
    self:put(function(bb, ox, oy) bb:paintBorder(ox + x, oy + y, w, h, bw or px(2), BLACK, r or 0) end)
end

-- keep_look: a picture (a cover) keeps its look in night mode; false: a drawing that inverts.
function Canvas:image(file, x, y, w, h, keep_look)
    local ok, iw = pcall(ImageWidget.new, ImageWidget, { file = file, width = w, height = h, scale_factor = 0,
                                                       alpha = keep_look == false, original_in_nightmode = keep_look ~= false })
    if not ok or not iw then return end
    self:put(function(bb, ox, oy)
        local sz = iw:getSize()
        iw:paintTo(bb, ox + x + math.floor((w - sz.w) / 2), oy + y + math.floor((h - sz.h) / 2))
    end)
end

function Canvas:bar(x, y, w, h, frac)
    local r = math.floor(h / 2)
    self:put(function(bb, ox, oy)
        bb:paintBorder(ox + x, oy + y, w, h, px(2), BLACK, r)
        local fw = math.floor((w - 2 * px(2)) * math.max(0, math.min(1, frac or 0)))
        if fw > 0 then bb:paintRoundedRect(ox + x + px(2), oy + y + px(2), math.max(fw, h - 2 * px(2)), h - 2 * px(2), BLACK, r) end
    end)
end

function Canvas:pill(x, y, w, h, filled)
    self:put(function(bb, ox, oy)
        if filled then bb:paintRoundedRect(ox + x, oy + y, w, h, BLACK, math.floor(h / 2))
        else bb:paintBorder(ox + x, oy + y, w, h, px(3), BLACK, math.floor(h / 2)) end
    end)
end

function Canvas:dot(cx, cy, r)
    self:put(function(bb, ox, oy) bb:paintCircle(ox + cx, oy + cy, r, BLACK) end)
end

-- A cover, or the title set in type when there's none (or it isn't made yet: a cover being opened
-- in the background is drawn when it comes, coverReady). Returns whether there was a cover, and
-- C.cover's reason when not.
function Canvas:coverOrTitle(book, x, y, w, h, make)
    local path, why = C.cover(book, w, h, make)
    if path then
        self:image(path, x, y, w, h, true)
        self:frame(x, y, w, h)
        return true
    end
    if why == "pending" and book.key then
        self.wants = self.wants or {}
        self.wants[book.key] = Geom:new{ x = x, y = y, w = w, h = h }
    end
    self:frame(x, y, w, h)
    local big = w > px(250)
    local pad = big and px(20) or px(8)
    local tsize, asize = big and 32 or 19, big and 22 or 15
    local tl = self:lineHeight(SERIF, tsize, w - 2 * pad)
    local al = self:lineHeight(SANS, asize, w - 2 * pad)
    local lines = math.max(1, math.min(5, math.floor((h * 0.62) / tl)))
    local ty = y + math.floor(h * 0.16)
    local th = self:box(C.shortTitle(book.title), SERIF, tsize, x + pad, ty, w - 2 * pad, lines, { align = "center", bold = true })
    if book.author then
        local room = math.floor((y + h - pad - (ty + th + px(10))) / al)
        self:box(book.author, SANS, asize, x + pad, ty + th + px(10), w - 2 * pad, math.min(2, room), { align = "center", color = MID })
    end
    return false, why
end

-- Covers that were being opened came in: the places waiting for them are drawn again.
function Canvas:coverReady(keys)
    local wants = self.wants or {}
    local regions = {}
    for _i, k in ipairs(keys) do
        if wants[k] then table.insert(regions, wants[k]) end
    end
    if #regions == 0 then return end
    self.partial = true
    self:layout()
    self.partial = false
    for _i, r in ipairs(regions) do
        UIManager:setDirty(self, function() return "ui", r end)
    end
end

-- The time, the date (with the Hebrew date once Daf has said it today), the battery; `title`
-- replaces the date.
function Canvas:statusLine(title)
    local W = self.dimen.w
    local L, R = px(56), W - px(56)
    local daf = self.daf
    local now = os.time() + (tonumber(daf.settings:readSetting("tz_offset")) or -25200)
    self:text(os.date("!%H:%M", now), SANS, 26, L, px(22))
    local mid = title
    if not mid then
        mid = os.date("!%A ", now) .. tonumber(os.date("!%d", now)) .. os.date("! %B", now)
        local home = daf:home()
        if daf:homeIsToday() and home.hebrew_date then mid = mid .. " · " .. home.hebrew_date end
    end
    self:text(mid, SANS, 26, math.floor(W / 2), px(22), { align = "center", bold = true, max_w = W - px(420) })
    local cap = Device:hasBattery() and Device:getPowerDevice():getCapacity() or nil
    if cap then
        local bx = R - px(50)
        self:put(function(bb, ox, oy)
            bb:paintBorder(ox + bx, oy + px(26), px(44), px(24), px(3), BLACK, px(4))
            bb:paintRect(ox + bx + px(44), oy + px(32), px(4), px(12), BLACK)
            local fw = math.floor((px(44) - px(10)) * cap / 100)
            if fw > 0 then bb:paintRect(ox + bx + px(5), oy + px(31), fw, px(14), BLACK) end
        end)
        self:text(cap .. "%", SANS, 26, bx - px(12), px(22), { align = "right" })
    end
    self:rect(0, px(74), W, px(2))
    return px(76)
end

-- The bar at the bottom. Returns where it starts.
function Canvas:navBar(active)
    local W, H = self.dimen.w, self.dimen.h
    local top = H - px(116)
    self:rect(0, top, W, px(2))
    local tabs = {
        { "home", _("Home"), function() self:goHomeScreen() end },
        { "shelves", _("Shelves"), function() self:openShelf(C.homeDir()) end },
        { "history", _("History"), function() self:history() end },
        { "daf", _("Daf"), function() self.daf:showScreen() end },
        { "search", _("Search"), function() self:search() end },
    }
    local tw = math.floor(W / #tabs)
    for i, t in ipairs(tabs) do
        local x = (i - 1) * tw
        local on = t[1] == active
        if on then self:put(function(bb, ox, oy) bb:paintRoundedRect(ox + x + math.floor(tw * 0.3), oy + top, math.floor(tw * 0.4), px(8), BLACK, px(4)) end) end
        self:image(C.PLUGIN_DIR .. "icons/" .. t[1] .. ".svg", x + math.floor((tw - px(46)) / 2), top + px(20), px(46), px(46), false)
        self:text(t[2], SANS, 21, x + math.floor(tw / 2), top + px(72), { align = "center", bold = on })
        self:tap(x, top, tw, H - top, t[3])
    end
    return top
end

-- ---------------------------------------------------------------- painting, taps, the clock

function Canvas:paintTo(bb, x, y)
    self.dimen.x, self.dimen.y = x, y
    bb:paintRect(x, y, self.dimen.w, self.dimen.h, WHITE)
    for _i, fn in ipairs(self.ops) do
        local ok, err = pcall(fn, bb, x, y)
        if not ok then logger.warn("[Daf] paint:", err) end
    end
end

-- KOReader's menu, as in the file browser: a swipe down from the top edge, or a tap on the
-- status line (its own setting decides which; the tab under the finger opens).
function Canvas:inTopZone(ges)
    return ges.pos.y - self.dimen.y < px(110)
end

function Canvas:showMenu(ges, swipe)
    local menu = C.fileMenu(self:ui())
    if not menu then return false end
    if swipe then menu:onSwipeShowMenu(ges) else menu:onTapShowMenu(ges) end
    return true
end

function Canvas:onSwipe(_arg, ges)
    if ges.direction == "south" and self:inTopZone(ges) then return self:showMenu(ges, true) or true end
    return self:onPageSwipe(ges)
end

function Canvas:onPageSwipe(_ges) return true end

-- KOReader's gestures (Settings → Taps and gestures → Gesture manager): the corners, the edges,
-- two fingers, multiswipes. They belong to the file browser (or the book) under this screen, which
-- never sees a touch while this is up; so one that has an action set goes to it first, the way the
-- file browser itself puts them before its own taps. The rest are this screen's.
local function hasAction(set)
    if type(set) ~= "table" then return false end
    for k in pairs(set) do
        if k ~= "settings" then return true end
    end
    return false
end

function Canvas:koGesture(ev)
    local ui = self:ui()
    local g = ui and ui.gestures
    if not (g and type(g.gestures) == "table" and ui._ordered_touch_zones) then return false end
    for _i, tz in ipairs(ui._ordered_touch_zones) do
        local id = tz.def and tz.def.id
        local has
        if id == "multiswipe" then has = g.multiswipes_enabled == true else has = id and hasAction(g.gestures[id]) end
        if has and tz.gs_range:match(ev) then
            local ok, done = pcall(tz.handler, ev)
            if ok and done then return true end
        end
    end
    return false
end

-- A tap or hold on one of this screen's buttons is the button's (the bar at the bottom sits in
-- KOReader's bottom corners); anything else goes to KOReader's gestures first. Every touch stops
-- here, so none reaches the file list hidden underneath.
function Canvas:onGesture(ev)
    if (ev.ges == "tap" or ev.ges == "hold") and self:target(ev, ev.ges == "hold") then return true end
    if self:koGesture(ev) then return true end
    InputContainer.onGesture(self, ev)
    return true
end

-- What a gesture does (night mode, the frontlight, Wi-Fi, a quick menu's choice…) is sent as an
-- event to the screen on top, this one. KOReader's handlers for it are in the file browser (or the
-- book) underneath, so while this is up that one is "always active", KOReader's own way of letting
-- a screen below hear what the top one leaves (Dispatcher events).
function Canvas:relayOn()
    local ui = self:ui()
    if ui and not ui.is_always_active then
        ui.is_always_active, ui._daf_relay = true, true
    end
end

function Canvas:relayOff()
    for _i, win in ipairs(UIManager._window_stack) do
        local w = win.widget
        if w ~= self and w.relayOn == Canvas.relayOn then return end      -- another of these is still up
    end
    local uis = { self:fm() or false, require("apps/reader/readerui").instance or false }
    for _i, ui in ipairs(uis) do
        if ui and ui._daf_relay then ui.is_always_active, ui._daf_relay = nil, nil end
    end
end

-- Runs the button under the touch, if there is one.
function Canvas:target(ges, hold)
    local x, y = ges.pos.x - self.dimen.x, ges.pos.y - self.dimen.y
    for i = #self.taps, 1, -1 do
        local t = self.taps[i]
        if x >= t.x and x < t.x + t.w and y >= t.y and y < t.y + t.h and (not hold or t.hold) then
            if hold then t.hold() else t.cb() end
            return true
        end
    end
    return false
end

function Canvas:hit(ges, hold)
    if not hold and ges.pos.y - self.dimen.y < px(76) then return self:showMenu(ges, false) or true end
    return self:target(ges, hold) or true
end

function Canvas:onTap(_arg, ges) return self:hit(ges, false) end
function Canvas:onHold(_arg, ges) return self:hit(ges, true) end

-- partial: only part of the screen is drawn again, so layout makes no covers that would land
-- outside it.
function Canvas:update(region)
    self.partial = region ~= nil
    self:layout()
    self.partial = false
    UIManager:setDirty(self, function() return "ui", region or self.dimen end)
end

-- The clock moves on the minute, while the screen is up.
function Canvas:tick()
    if not UIManager:isWidgetShown(self) then return end
    self:update(Geom:new{ x = 0, y = 0, w = self.dimen.w, h = px(76) })
    self:scheduleTick()
end

function Canvas:scheduleTick()
    UIManager:unschedule(self.tick_fn)
    self.tick_fn = self.tick_fn or function() self:tick() end
    UIManager:scheduleIn(61 - (os.time() % 60), self.tick_fn)
end

function Canvas:onShow()
    shown[self] = true
    self:relayOn()
    self:scheduleTick()
    UIManager:setDirty(self, function() return "full", self.dimen end)
end

function Canvas:onCloseWidget()
    self:relayOff()
    shown[self] = nil
    if self.tick_fn then UIManager:unschedule(self.tick_fn) end
end

function Canvas:onResume()
    if UIManager:isWidgetShown(self) then self:update() end
end

function Canvas:onClose()
    UIManager:close(self)
    return true
end

-- ---------------------------------------------------------------- going places

-- The file browser; and what has the menu, history and search: the file browser, or the book's
-- reader when this is up over a book (a gesture, or the Daf tab from a book's menu).
function Canvas:fm()
    return require("apps/filemanager/filemanager").instance
end

function Canvas:ui()
    return self:fm() or require("apps/reader/readerui").instance
end

function Canvas:openBook(file)
    self.daf:closeCanvases(nil)
    UIManager:close(self)
    local reader = require("apps/reader/readerui")
    local cur = reader.instance
    if cur and cur.document then
        if cur.document.file ~= file then UIManager:nextTick(function() cur:switchDocument(file) end) end
        return
    end
    reader:showReader(file)
end

function Canvas:goHomeScreen()
    UIManager:close(self)
    self.daf:showHome()
end

function Canvas:openShelf(path)
    UIManager:close(self)
    self.daf:showShelf(path)
end

function Canvas:fileBrowser(path)
    self.daf:closeCanvases(nil)
    UIManager:close(self)
    local FileManager = require("apps/filemanager/filemanager")
    local fm = self:fm()
    if fm and fm.file_chooser then return fm.file_chooser:changeToPath(path) end
    local cur = require("apps/reader/readerui").instance
    if cur then
        -- the book closes; the file browser opens at the folder, not Home
        C.skip_home_once = true
        cur:onClose()
        UIManager:nextTick(function()
            local now = FileManager.instance
            if now and now.file_chooser then now.file_chooser:changeToPath(path) else FileManager:showFiles(path) end
        end)
        return
    end
    FileManager:showFiles(path)
end

function Canvas:history()
    local ui = self:ui()
    if ui and ui.history then ui.history:onShowHist() end
end

function Canvas:search()
    local ui = self:ui()
    if ui and ui.filesearcher then ui.filesearcher:onShowFileSearch() end
end

return Canvas
