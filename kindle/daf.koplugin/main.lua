--[[
Daf for KOReader.

  * Sends new page turns from KOReader's statistics database to Daf on morten
    when the Kindle goes to sleep, closes a book, or comes online, and with them each
    book's highlights and notes from its KOReader notes file (sendHighlights).
  * Keeps the sleep-screen message current: today's minutes toward the hour,
    the Kindle's own minutes (always fresh) plus every other source's minutes
    from the last time Daf answered.

  * From Daf to the Kindle: when a book opens, if Daf has Nathan further along (read in
    Daf's book reader since he last read it here), offer to go there; and add the
    highlights he made in Daf as KOReader highlights, with their notes. Each is added once.
  * The Daf tab (dafscreen.lua): today, the day's review with Keep and Less often, the
    nightstand, and opening a book from it. From the bar, Tools → Daf → Open Daf, or a
    gesture. Works offline from the last answer; taps are queued.
  * Home (home.lua) and the shelves (shelf.lua), drawn with canvas.lua, with book covers from
    covers.lua (made ahead for the whole library after Home appears); and outside a book,
    the book's global settings in KOReader's menu too (readerprefs.lua).

Settings live in settings/daf.lua (url, token, sleep_screen, last_start, cache, home,
pending_review, paths, show_on_wake).
Nothing here edits settings.reader.lua directly; the screensaver message is set
through G_reader_settings in memory, which KOReader saves itself.
]]
local Covers = require("covers")
local DataStorage = require("datastorage")
local DafScreen = require("dafscreen") -- must load here, while the plugin folder is on package.path
local Home = require("home")
local ReaderPrefs = require("readerprefs")
local Shelf = require("shelf")
local Dispatcher = require("dispatcher")
local Event = require("ui/event")
local InfoMessage = require("ui/widget/infomessage")
local LuaSettings = require("luasettings")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local logger = require("logger")
local _ = require("gettext")

local STATS_DB = DataStorage:getSettingsDir() .. "/statistics.sqlite3"
local GOAL = 60 -- until Daf says otherwise: the day's minutes goal comes with /api/kindle/home
local REFRESH_EVERY = 120 -- seconds between sleep-message updates while reading

local Daf = WidgetContainer:extend{
    name = "daf",
    is_doc_only = false,
    GOAL = GOAL,
}

function Daf:init()
    self.settings = LuaSettings:open(DataStorage:getSettingsDir() .. "/daf.lua")
    self.last_refresh = 0
    self.ui.menu:registerToMainMenu(self)
    Dispatcher:registerAction("daf_send", { category = "none", event = "DafSend", title = _("Daf: send reading time"), general = true })
    Dispatcher:registerAction("daf_show", { category = "none", event = "DafShow", title = _("Daf: open the Daf screen"), general = true })
    Dispatcher:registerAction("daf_home", { category = "none", event = "DafHome", title = _("Daf: open Home"), general = true })
    UIManager:scheduleIn(3, function() self:refreshSleepMessage() end)
    -- The file browser's house icon (Project: Title's too) opens Home; Home's Shelves goes to the
    -- folders. Done once, on the file browser's class.
    local FileManager = require("apps/filemanager/filemanager")
    if not FileManager._daf_goHome then
        FileManager._daf_goHome = FileManager.goHome
        FileManager.goHome = function(fm, ...)
            local daf = fm.daf
            if daf and daf.settings and daf.settings:readSetting("home_on_start") ~= false then
                daf:showHome()
                return true
            end
            return FileManager._daf_goHome(fm, ...)
        end
    end
    -- Shelves and KOReader's file actions: a shelf redraws after them, and the long-press dialog
    -- (in the browser, history, collections and search too) has Move to shelf….
    require("canvas").C.watchFiles()
    if self.ui and self.ui.addFileDialogButtons and not self.ui.document then
        local ui = self.ui
        ui:addFileDialogButtons("daf_move", function(file, is_file)
            local cur = ui.file_chooser and ui.file_chooser.path
            if not is_file and (file:match("/%.%.$") or (cur and cur:match("^(.*)/[^/]+$") == file)) then return nil end
            return { {
                text = _("Move to shelf…"),
                callback = function()
                    local top = UIManager:getTopmostVisibleWidget()
                    if top then UIManager:close(top) end
                    Shelf.pickShelf(file, is_file)
                end,
            } }
        end)
    end
    -- Home comes up over the file browser: when KOReader starts, and when a book closes. (Checked
    -- a moment later: the file browser isn't finished building while its plugins start.)
    local Canvas = require("canvas")
    local skip = Canvas.C.skip_home_once
    Canvas.C.skip_home_once = nil
    if self.ui and not self.ui.document and not skip and self.settings:readSetting("home_on_start") ~= false then
        UIManager:scheduleIn(0.2, function()
            if self.ui and self.ui.file_chooser and not self.ui.document then self:showHome() end
        end)
    end
end


-- ---------------------------------------------------------------- statistics

local function flushStatistics()
    local ok, ReaderUI = pcall(require, "apps/reader/readerui")
    local ui = ok and ReaderUI and ReaderUI.instance
    if ui and ui.statistics and ui.statistics.is_doc then
        pcall(function() ui.statistics:insertDB() end)
    end
end

local function withStats(fn)
    local SQ3 = require("lua-ljsqlite3/init")
    local conn = SQ3.open(STATS_DB)
    local ok, a, b = pcall(fn, conn)
    conn:close()
    if not ok then
        logger.warn("[Daf] statistics query failed:", a)
        return nil
    end
    return a, b
end

function Daf:dayStart()
    local offset = tonumber(self.settings:readSetting("tz_offset")) or -25200
    local now = os.time()
    return math.floor((now + offset) / 86400) * 86400 - offset, offset
end

function Daf:kindleMinutesToday()
    local start = self:dayStart()
    local secs = withStats(function(conn)
        return conn:rowexec(string.format("SELECT COALESCE(SUM(duration), 0) FROM page_stat_data WHERE start_time >= %d", start))
    end)
    return (tonumber(secs) or 0) / 60
end

-- ---------------------------------------------------------------- the network

-- KOReader's json decodes null as a function (json.null); drop those, so answers can be
-- tested for nil and saved with LuaSettings.
local function denull(v)
    if type(v) ~= "table" then return v end
    for k, x in pairs(v) do
        if type(x) == "function" then v[k] = nil else denull(x) end
    end
    return v
end

local function request(method, url, token, body)
    local http = require("socket.http")
    local ltn12 = require("ltn12")
    local socket = require("socket")
    local socketutil = require("socketutil")
    local JSON = require("json")
    local sink = {}
    local headers = { ["Authorization"] = "Bearer " .. token, ["Accept"] = "application/json" }
    local source
    if body then
        local data = JSON.encode(body)
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = tostring(#data)
        source = ltn12.source.string(data)
    end
    socketutil:set_timeout(5, 15)
    local code, resp_headers = socket.skip(1, http.request({ url = url, method = method, headers = headers, source = source, sink = ltn12.sink.table(sink) }))
    socketutil:reset_timeout()
    if resp_headers == nil or code ~= 200 then
        return nil, code
    end
    local ok, result = pcall(JSON.decode, table.concat(sink))
    if ok then return denull(result) end
    return nil, "bad json"
end

local function online()
    local ok, res = pcall(function()
        local NetworkMgr = require("ui/network/manager")
        return NetworkMgr:isWifiOn() and NetworkMgr:isConnected()
    end)
    return ok and res
end

function Daf:configured()
    return self.settings:readSetting("url") and self.settings:readSetting("token")
end

-- Page turns newer than the last batch Daf accepted, in batches of 4000.
function Daf:pendingPages()
    local since = math.floor(tonumber(self.settings:readSetting("last_start")) or (os.time() - 14 * 86400))
    return withStats(function(conn)
        local res, n = conn:exec(string.format([[
            SELECT b.md5, b.title, b.authors, p.start_time, p.duration, p.page, p.total_pages
            FROM page_stat_data p JOIN book b ON b.id = p.id_book
            WHERE p.start_time > %d AND b.md5 IS NOT NULL
            ORDER BY p.start_time LIMIT 4000]], since))
        local books, pages, seen, newest = {}, {}, {}, since
        for i = 1, (n or 0) do
            local md5 = res[1][i]
            if not seen[md5] then
                seen[md5] = true
                table.insert(books, { md5 = md5, title = res[2][i], authors = res[3][i] })
            end
            local start = tonumber(res[4][i])
            table.insert(pages, { md5 = md5, start = start, duration = tonumber(res[5][i]), page = tonumber(res[6][i]), total = tonumber(res[7][i]) })
            if start > newest then newest = start end
        end
        return { books = books, pages = pages }, newest
    end)
end

function Daf:send(quiet)
    if not self:configured() then
        if not quiet then UIManager:show(InfoMessage:new{ text = _("Daf isn't set up on this Kindle yet."), timeout = 4 }) end
        return false
    end
    flushStatistics()
    local url, token = self.settings:readSetting("url"), self.settings:readSetting("token")
    local sent = 0
    for _round = 1, 10 do
        local batch, newest = self:pendingPages()
        if not batch or #batch.pages == 0 then break end
        local res, err = request("POST", url .. "/api/kindle/pages", token, batch)
        if not res then
            logger.warn("[Daf] send failed:", err)
            if not quiet then UIManager:show(InfoMessage:new{ text = _("Couldn't reach Daf. It will try again next time."), timeout = 4 }) end
            return false
        end
        sent = sent + #batch.pages
        self.settings:saveSetting("last_start", newest)
        self.settings:flush()
        if #batch.pages < 4000 then break end
    end
    local ok_h, books = pcall(function() return self:sendHighlights() end)
    if not ok_h then logger.warn("[Daf] highlights:", books); books = 0 end
    self:fetchToday()
    self:refreshSleepMessage(true)
    if not quiet then
        local text = sent > 0 and string.format(_("Sent %d page turns to Daf."), sent) or _("Daf is up to date.")
        if books > 0 then text = text .. " " .. string.format(_("Highlights from %d books too."), books) end
        UIManager:show(InfoMessage:new{ text = text, timeout = 3 })
    end
    return true
end

-- ---------------------------------------------------------------- highlights, Kindle to Daf
-- Each book's highlights and notes live in its KOReader notes file (book.sdr/metadata.*.lua).
-- Daf used to read those from Syncthing's copy on morten and from KoInsight; now the plugin sends
-- them: the open book as it is in memory, and every book in the history whose notes file changed
-- since it was last sent (the first time, all of them, a few batches per send). Daf keeps the
-- newest per book and reads them on its next sync.
local NOTES_BATCH = 15

local function hasAny(t)
    return type(t) == "table" and next(t) ~= nil
end

function Daf:liveBook()
    local ui = self.ui
    if not (ui and ui.document and ui.doc_settings and ui.annotation) then return nil end
    local md5 = ui.doc_settings:readSetting("partial_md5_checksum")
    if not md5 then return nil end
    local props = ui.doc_props or ui.doc_settings:readSetting("doc_props") or {}
    return { md5 = md5, file = ui.document.file, title = props.title or props.display_title,
             authors = props.authors, annotations = ui.annotation.annotations or {} }
end

function Daf:changedBooks(limit, sent, skip_file)
    local DocSettings = require("docsettings")
    local ReadHistory = require("readhistory")
    local lfs = require("libs/libkoreader-lfs")
    local out = {}
    for _i, item in ipairs(ReadHistory.hist or {}) do
        local file = item.file
        if file and file ~= skip_file then
            local sidecar = DocSettings:findSidecarFile(file)
            local mtime = sidecar and lfs.attributes(sidecar, "modification")
            if mtime and sent[file] ~= mtime then
                local ok, ds = pcall(DocSettings.openSettingsFile, sidecar)
                local data = ok and ds and ds.data or {}
                local props = data.doc_props or {}
                if data.partial_md5_checksum and (hasAny(data.annotations) or sent[file]) then
                    table.insert(out, { file = file, mtime = mtime, book = {
                        md5 = data.partial_md5_checksum, file = file, title = props.title, authors = props.authors,
                        annotations = data.annotations or {} } })
                else
                    sent[file] = mtime          -- no highlights, never sent: nothing to say until it changes
                end
                if #out >= limit then break end
            end
        end
    end
    return out
end

function Daf:sendHighlights()
    if not self:configured() then return 0 end
    local url, token = self.settings:readSetting("url"), self.settings:readSetting("token")
    local sent = self.settings:readSetting("notes_sent") or {}
    local n = 0
    local live = self:liveBook()
    if live and (hasAny(live.annotations) or sent[live.file]) then
        if request("POST", url .. "/api/kindle/annotations", token, { books = { live } }) then
            sent[live.file] = sent[live.file] or 0
            n = n + 1
        else
            return n
        end
    end
    for _round = 1, 4 do
        local batch = self:changedBooks(NOTES_BATCH, sent, live and live.file)
        if #batch == 0 then break end
        local books = {}
        for _j, x in ipairs(batch) do table.insert(books, x.book) end
        if not request("POST", url .. "/api/kindle/annotations", token, { books = books }) then break end
        for _j, x in ipairs(batch) do sent[x.file] = x.mtime end
        n = n + #batch
        if #batch < NOTES_BATCH then break end
    end
    self.settings:saveSetting("notes_sent", sent)
    self.settings:flush()
    return n
end

function Daf:fetchToday()
    if not self:configured() then return end
    local url, token = self.settings:readSetting("url"), self.settings:readSetting("token")
    local res = request("GET", url .. "/api/kindle/home", token)
    if res then
        res.fetched = os.time()
        self.settings:saveSetting("home", res)
    else
        res = request("GET", url .. "/api/kindle/today", token)
    end
    if res then
        self.settings:saveSetting("tz_offset", res.tz_offset)
        self.settings:saveSetting("cache", { date = res.date, other = res.other or 0, year_day = res.year_day, year_hours = res.year_hours,
                                             goal = res.goal, main = res.main, fetched = os.time() })
        self.settings:flush()
    end
end

-- ---------------------------------------------------------------- the Daf screen's data

function Daf:home()
    return self.settings:readSetting("home") or {}
end

function Daf:localDate()
    local offset = tonumber(self.settings:readSetting("tz_offset")) or -25200
    return os.date("!%Y-%m-%d", os.time() + offset)
end

function Daf:homeIsToday()
    return self:home().date == self:localDate()
end

function Daf:pendingCount()
    return #(self.settings:readSetting("pending_review") or {})
end

-- Keep / Less often from the screen. The cached review item was already marked by the
-- screen (it holds the same table); this remembers the tap until Daf has it.
function Daf:queueReview(id, action)
    local pending = self.settings:readSetting("pending_review") or {}
    for i = #pending, 1, -1 do
        if pending[i].id == id then table.remove(pending, i) end
    end
    table.insert(pending, { id = id, action = action })
    self.settings:saveSetting("pending_review", pending)
    self.settings:flush()
    if online() then
        UIManager:scheduleIn(1, function()
            pcall(function() self:flushReview() end)
            if self.screen and UIManager:isWidgetShown(self.screen) then self.screen:update() end
        end)
    end
end

function Daf:flushReview()
    local pending = self.settings:readSetting("pending_review") or {}
    if #pending == 0 or not self:configured() then return true end
    local res = request("POST", self.settings:readSetting("url") .. "/api/kindle/review", self.settings:readSetting("token"), { actions = pending })
    if res then
        self.settings:delSetting("pending_review")
        self.settings:flush()
        return true
    end
    return false
end

-- Where this Kindle last was in a book, from KOReader's own statistics.
function Daf:localProgress(md5s)
    local list = {}
    for _i, m in ipairs(md5s) do
        if type(m) == "string" and m:match("^%x+$") then table.insert(list, "'" .. m .. "'") end
    end
    if #list == 0 then return nil end
    local page, total = withStats(function(conn)
        local res, n = conn:exec(string.format([[
            SELECT p.page, p.total_pages FROM page_stat_data p JOIN book b ON b.id = p.id_book
            WHERE b.md5 IN (%s) ORDER BY p.start_time DESC LIMIT 1]], table.concat(list, ",")))
        if not n or n == 0 then return nil end
        return tonumber(res[1][1]), tonumber(res[2][1])
    end)
    return page, total
end

-- The file for a nightstand book: by KOReader's partial md5 over the reading history,
-- then by title in the file name. Found paths are remembered.
function Daf:findFile(md5s, title)
    local lfs = require("libs/libkoreader-lfs")
    local util = require("util")
    local paths = self.settings:readSetting("paths") or {}
    for _i, m in ipairs(md5s) do
        local f = paths[m]
        if f and lfs.attributes(f, "mode") == "file" then return f end
    end
    local want = {}
    for _i, m in ipairs(md5s) do want[m] = true end
    local ReadHistory = require("readhistory")
    local found
    for _i, item in ipairs(ReadHistory.hist or {}) do
        if item.file and lfs.attributes(item.file, "mode") == "file" then
            local ok, h = pcall(util.partialMD5, item.file)
            if ok and h and want[h] then
                found = item.file
                paths[h] = found
                break
            end
        end
    end
    if not found and title then
        local key = (title:gsub("%s*[:%(].*$", "")):lower():gsub("[^%w]", "")
        if #key >= 4 then
            for _i, item in ipairs(ReadHistory.hist or {}) do
                local name = (item.text or ""):lower():gsub("[^%w]", "")
                if name:find(key, 1, true) and lfs.attributes(item.file, "mode") == "file" then
                    found = item.file
                    break
                end
            end
        end
    end
    self.settings:saveSetting("paths", paths)
    self.settings:flush()
    return found
end

function Daf:openBook(book, screen)
    local file = self:findFile(book.md5s or {}, book.title)
    if not file then
        UIManager:show(InfoMessage:new{ text = _("That book isn't in this Kindle's history. Open it once from the library, and Daf will find it after that."), timeout = 5 })
        return
    end
    if screen then UIManager:close(screen) end
    local ReaderUI = require("apps/reader/readerui")
    local cur = ReaderUI.instance
    if cur and cur.document and cur.document.file == file then return end
    UIManager:nextTick(function()
        if cur then cur:switchDocument(file) else ReaderUI:showReader(file) end
    end)
end

-- ---------------------------------------------------------------- Daf → the Kindle

function Daf:docMd5()
    local ok, md5 = pcall(function() return self.ui.doc_settings:readSetting("partial_md5_checksum") end)
    if ok and type(md5) == "string" and md5 ~= "" then return md5 end
    local ok2, h = pcall(require("util").partialMD5, self.ui.document.file)
    return ok2 and h or nil
end

function Daf:lastReadHere(md5)
    return tonumber(withStats(function(conn)
        return conn:rowexec(string.format(
            "SELECT COALESCE(MAX(p.start_time + p.duration), 0) FROM page_stat_data p JOIN book b ON b.id = p.id_book WHERE b.md5 = '%s'", md5))
    end)) or 0
end

function Daf:onReaderReady()
    if not self.ui.document or not self:configured() then return end
    UIManager:scheduleIn(2, function() pcall(function() self:syncFromDaf(false) end) end)
end

function Daf:syncFromDaf(manual)
    if not self.ui.document then return end
    if not online() then
        if manual then UIManager:show(InfoMessage:new{ text = _("Turn on Wi-Fi to reach Daf."), timeout = 3 }) end
        return
    end
    local md5 = self:docMd5()
    if not md5 or not md5:match("^%x+$") then return end
    local res = request("GET", self.settings:readSetting("url") .. "/api/kindle/book?md5=" .. md5, self.settings:readSetting("token"))
    if not res or not res.known then
        if manual then UIManager:show(InfoMessage:new{ text = _("Daf doesn't know this book yet. It will after the next sync."), timeout = 4 }) end
        return
    end
    local added = self:pushHighlights(res.highlights or {})
    local offered = self:offerPosition(md5, res.daf)
    if manual and added == 0 and not offered then
        UIManager:show(InfoMessage:new{ text = _("Nothing new from Daf for this book."), timeout = 3 })
    end
end

-- Find a passage Daf saved: the first words give the start, the last words the end.
function Daf:locate(text)
    local doc = self.ui.document
    local words = {}
    for w in tostring(text):gmatch("%S+") do table.insert(words, w) end
    if #words == 0 then return nil end
    -- findAllText searches the whole book (findText "from the start" finds nothing on 2025.04).
    local head = table.concat(words, " ", 1, math.min(#words, 10))
    local ok, res = pcall(doc.findAllText, doc, head, true, 0, 20, false)
    if not ok or type(res) ~= "table" or not res[1] then return nil end
    if #words <= 10 then return res[1].start, res[1]["end"] end
    local tail = table.concat(words, " ", math.max(1, #words - 7), #words)
    for _i, first in ipairs(res) do
        local ok2, res2 = pcall(doc.findAllText, doc, tail, true, 0, 100, false)
        if ok2 and type(res2) == "table" then
            for _j, r in ipairs(res2) do
                local cmp = doc:compareXPointers(first.start, r.start)
                if cmp and cmp >= 0 then return first.start, r["end"] end
            end
        end
    end
    return nil
end

function Daf:pushHighlights(list)
    if #list == 0 or not self.ui.rolling or not self.ui.annotation then return 0 end
    local pushed = self.settings:readSetting("pushed_hl") or {}
    local acks, added, missed = {}, 0, 0
    for _i, h in ipairs(list) do
        if pushed[h.id] then
            table.insert(acks, h.id)
        else
            local pos0, pos1 = self:locate(h.text or "")
            if pos0 and pos1 then
                local hl = self.view.highlight or {}
                local item = {
                    page = pos0, pos0 = pos0, pos1 = pos1, text = h.text,
                    drawer = hl.saved_drawer or "lighten", color = hl.saved_color or "gray",
                    chapter = self.ui.toc:getTocTitleByPage(pos0),
                    note = (h.note and h.note ~= "") and h.note or nil,
                }
                local index = self.ui.annotation:addItem(item)
                self.ui:handleEvent(Event:new("AnnotationsModified", { item, nb_highlights_added = 1, nb_notes_added = item.note and 1 or nil, index_modified = index }))
                pushed[h.id] = true
                table.insert(acks, h.id)
                added = added + 1
            else
                missed = missed + 1
            end
        end
    end
    self.settings:saveSetting("pushed_hl", pushed)
    self.settings:flush()
    if #acks > 0 then
        request("POST", self.settings:readSetting("url") .. "/api/kindle/highlights/ack", self.settings:readSetting("token"), { ids = acks })
    end
    if added > 0 then
        UIManager:setDirty(self.view.dialog, "ui")
        UIManager:show(InfoMessage:new{ text = string.format(added == 1 and _("Added a highlight you made in Daf.") or _("Added %d highlights you made in Daf."), added)
            .. (missed > 0 and "\n" .. string.format(_("%d couldn't be found in this edition."), missed) or ""), timeout = 4 })
    end
    return added
end

function Daf:offerPosition(md5, daf)
    if type(daf) ~= "table" or not daf.fraction or not daf.updated then return false end
    if daf.updated <= self:lastReadHere(md5) + 60 then return false end
    local declined = self.settings:readSetting("declined_pos") or {}
    if declined[md5] == daf.updated then return false end
    local page, total = self.view.state.page, self.ui.document:getPageCount()
    local here = (page and total and total > 0) and page / total or 0
    if math.abs(daf.fraction - here) < 0.01 then return false end
    local offset = tonumber(self.settings:readSetting("tz_offset")) or -25200
    local when = os.date("!%b %d, %H:%M", daf.updated + offset)
    local where = string.format("%d%%", math.floor(daf.fraction * 100 + 0.5)) .. (daf.chapter and (", “" .. daf.chapter .. "”") or "")
    local ConfirmBox = require("ui/widget/confirmbox")
    UIManager:show(ConfirmBox:new{
        text = string.format(_("You read further in Daf: %s (%s).\n\nGo there?"), where, when),
        ok_text = _("Go there"),
        cancel_text = _("Stay here"),
        ok_callback = function() self.ui:handleEvent(Event:new("GotoPercent", daf.fraction * 100)) end,
        cancel_callback = function()
            declined[md5] = daf.updated
            self.settings:saveSetting("declined_pos", declined)
            self.settings:flush()
        end,
    })
    return true
end

-- Home and the shelves are one at a time: a new one closes the one before, so none pile up
-- under the file browser.
function Daf:closeCanvases(keep)
    for _i, w in ipairs(self.canvases or {}) do
        if w ~= keep and UIManager:isWidgetShown(w) then UIManager:close(w) end
    end
    self.canvases = { keep }
end

function Daf:showHome()
    if self.home_screen and UIManager:isWidgetShown(self.home_screen) then
        self:closeCanvases(self.home_screen)
        return self.home_screen
    end
    self:closeCanvases(nil)
    flushStatistics()
    local ok, home = pcall(function() return Home:new{ daf = self } end)
    if not ok then
        logger.warn("[Daf] home:", home)
        return nil
    end
    self.home_screen = home
    self.canvases = { home }
    UIManager:show(home)
    self:coversAhead()
    local fetched = self:home().fetched or 0
    if online() and (not self:homeIsToday() or os.time() - fetched > 1800) then
        UIManager:scheduleIn(0.5, function() self:refreshHome(home, false) end)
    end
    return home
end

-- Every book's shelf-size cover, made ahead a few at a time once Home is up (covers.lua).
function Daf:coversAhead()
    pcall(function()
        local C = require("canvas").C
        local set = {}
        for _i, m in ipairs(self:home().private_md5s or {}) do set[m] = true end
        Covers.private = set
        local w, h = Shelf.usualCoverSize()
        Covers.sweep(C.allBooks(C.homeDir()), { { w, h } }, 3)
    end)
end

function Daf:showShelf(path)
    self:closeCanvases(nil)
    local ok, shelf = pcall(function() return Shelf:new{ daf = self, path = path } end)
    if not ok then
        logger.warn("[Daf] shelf:", shelf)
        return nil
    end
    self.canvases = { shelf }
    UIManager:show(shelf)
    return shelf
end

function Daf:onDafHome()
    self:showHome()
    return true
end

function Daf:showScreen()
    flushStatistics()
    self:closeCanvases(nil)
    local ok, screen = pcall(function() return DafScreen:new{ daf = self } end)
    if not ok then
        logger.warn("[Daf] screen:", screen)
        return nil
    end
    self.screen = screen
    self.canvases = { screen }
    UIManager:show(screen)
    self.settings:saveSetting("shown_day", self:localDate())
    self.settings:flush()
    if online() then
        UIManager:scheduleIn(0.5, function() self:refreshHome(screen, false) end)
    end
    return screen
end

-- Send what's waiting, fetch the newest, redraw. With ask, turn Wi-Fi on if needed.
function Daf:refreshHome(screen, ask)
    local function go()
        pcall(function()
            self:flushReview()
            self:send(true)
        end)
        if screen and UIManager:isWidgetShown(screen) then
            if screen.firstOpen then screen.idx = screen:firstOpen() end
            screen:update()
        end
    end
    if ask then
        require("ui/network/manager"):runWhenOnline(go)
    elseif online() then
        go()
    end
end

-- ---------------------------------------------------------------- the sleep screen

-- The day's minutes goal from Daf (Preferences → Goals), or an hour.
function Daf:goal()
    local cache = self.settings:readSetting("cache") or {}
    local g = tonumber(cache.goal)
    return (g and g > 0) and math.floor(g + 0.5) or GOAL
end

-- The main goal when it isn't minutes a day ("33 of 200 pages this week"), else nil.
function Daf:mainLine()
    local cache = self.settings:readSetting("cache") or {}
    local m = cache.main
    if type(m) ~= "table" or (m.kind == "minutes" and m.period == "day") or cache.date ~= self:localDate() then return nil end
    return m.text
end

function Daf:summary()
    local kindle = self:kindleMinutesToday()
    local cache = self.settings:readSetting("cache") or {}
    local other = 0
    local start = self:dayStart()
    if cache.date and cache.fetched and cache.fetched >= start then
        other = tonumber(cache.other) or 0
    end
    local total = kindle + other
    return { total = total, kindle = kindle, other = other, year_day = cache.year_day, year_hours = cache.year_hours }
end

function Daf:message()
    local s = self:summary()
    local first
    local goal = self:goal()
    if s.total >= goal then
        first = goal == 60 and string.format("That's the hour: %d minutes today", math.floor(s.total))
            or string.format("That's today's goal: %d minutes", math.floor(s.total))
    else
        first = string.format("%d of %d minutes today", math.floor(s.total), goal)
    end
    local main = self:mainLine()
    if main then first = first .. "\n" .. main end
    local second = s.year_day and string.format("Year 30, day %d · %s hours so far", s.year_day, tostring(s.year_hours or 0)) or "Year 30"
    return "Daf\n" .. first .. "\n" .. second
end

function Daf:refreshSleepMessage(force)
    if self.settings:readSetting("sleep_screen") == false then return end
    local now = os.time()
    if not force and now - self.last_refresh < REFRESH_EVERY then return end
    self.last_refresh = now
    if not self.settings:readSetting("orig_saved") then
        self.settings:saveSetting("orig_message", G_reader_settings:readSetting("screensaver_message"))
        self.settings:saveSetting("orig_show_message", G_reader_settings:isTrue("screensaver_show_message"))
        self.settings:saveSetting("orig_saved", true)
        self.settings:flush()
    end
    local ok, msg = pcall(function() return self:message() end)
    if ok and msg then
        G_reader_settings:saveSetting("screensaver_message", msg)
        G_reader_settings:makeTrue("screensaver_show_message")
    end
end

function Daf:setSleepScreen(on)
    self.settings:saveSetting("sleep_screen", on)
    self.settings:flush()
    if on then
        self:refreshSleepMessage(true)
    else
        local orig = self.settings:readSetting("orig_message")
        if orig then G_reader_settings:saveSetting("screensaver_message", orig) else G_reader_settings:delSetting("screensaver_message") end
        if self.settings:readSetting("orig_show_message") then G_reader_settings:makeTrue("screensaver_show_message") else G_reader_settings:makeFalse("screensaver_show_message") end
        self.settings:delSetting("orig_saved")
        self.settings:flush()
    end
end

-- ---------------------------------------------------------------- events

function Daf:onPageUpdate()
    self:refreshSleepMessage()
end

function Daf:onSuspend()
    flushStatistics()
    self:refreshSleepMessage(true)
    if online() then pcall(function() self:flushReview(); self:send(true) end) end
end

function Daf:onCloseDocument()
    if online() then pcall(function() self:send(true) end) end
    self:refreshSleepMessage(true)
end

function Daf:onNetworkConnected()
    UIManager:scheduleIn(2, function() pcall(function() self:flushReview(); self:send(true) end) end)
end

function Daf:onResume()
    self.last_refresh = 0
    -- Optionally, the first wake of the morning opens the Daf screen.
    if self.settings:isTrue("show_on_wake") and self.settings:readSetting("shown_day") ~= self:localDate() then
        local offset = tonumber(self.settings:readSetting("tz_offset")) or -25200
        local hour = tonumber(os.date("!%H", os.time() + offset))
        if hour >= 4 and hour < 12 then
            UIManager:scheduleIn(1, function() self:showScreen() end)
        end
    end
end

function Daf:onDafShow()
    self:showScreen()
end

function Daf:onDafSend()
    local NetworkMgr = require("ui/network/manager")
    NetworkMgr:runWhenOnline(function() self:send(false) end)
end

-- ---------------------------------------------------------------- menu

function Daf:addToMainMenu(menu_items)
    -- Outside a book, the book's own global settings too (readerprefs.lua).
    if not self.ui.document then ReaderPrefs.add(menu_items) end
    menu_items.daf = {
        text = _("Daf"),
        sorting_hint = "tools",
        sub_item_table = {
            {
                text = _("Home"),
                callback = function() self:showHome() end,
            },
            {
                text = _("Open Home when KOReader starts, after a book, and from the house icon"),
                checked_func = function() return self.settings:readSetting("home_on_start") ~= false end,
                callback = function()
                    self.settings:saveSetting("home_on_start", self.settings:readSetting("home_on_start") == false)
                    self.settings:flush()
                end,
            },
            {
                text = _("Open Daf"),
                callback = function() self:showScreen() end,
            },
            {
                text = _("Get my place and highlights from Daf"),
                enabled_func = function() return self.ui.document ~= nil end,
                callback = function() require("ui/network/manager"):runWhenOnline(function() self:syncFromDaf(true) end) end,
            },
            {
                text_func = function()
                    local ok, s = pcall(function() return self:summary() end)
                    if ok and s then return string.format(_("Today: %d of %d minutes"), math.floor(s.total), self:goal()) end
                    return _("Today")
                end,
                keep_menu_open = true,
                callback = function()
                    UIManager:show(InfoMessage:new{ text = self:message(), timeout = 6 })
                end,
            },
            {
                text = _("Send reading time and highlights now"),
                keep_menu_open = true,
                callback = function() self:onDafSend() end,
            },
            {
                text = _("Show today's minutes on the sleep screen"),
                checked_func = function() return self.settings:readSetting("sleep_screen") ~= false end,
                callback = function() self:setSleepScreen(self.settings:readSetting("sleep_screen") == false) end,
            },
            {
                text = _("Open Daf on the first wake of the morning"),
                checked_func = function() return self.settings:isTrue("show_on_wake") end,
                callback = function()
                    self.settings:saveSetting("show_on_wake", not self.settings:isTrue("show_on_wake"))
                    self.settings:flush()
                end,
            },
        },
    }
end

return Daf
