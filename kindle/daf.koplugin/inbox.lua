--[[
Books from Daf: what Daf has waiting for the Kindle (a book put on the Kindle from Daf, Send to
Kindle's articles), brought in on the Wi-Fi sync, since Syncthing is off on the Kindle.

On each sync (not the one as the Kindle goes to sleep), the Kindle tells Daf its shelves (the
folders in the home folder) and every book on them, by its path and KOReader's fingerprint (POST
/api/kindle/shelves), so Daf's Books has the same shelves (daf/kindleshelves.py). Daf answers
with the books it has moved to another shelf (or off every shelf, to the home folder), and the
Kindle moves them with KOReader's own bookkeeping, as Move to shelf… does: their notes, history
and collections go with them (POST /api/kindle/moves/<id>/done, with {path} or {error}).

Then it asks what's waiting (GET /api/kindle/inbox, oldest first). Each file goes into its
shelf, <home>/<shelf>/<name>, and the shelf is made if it isn't there. One already there at the same size is only marked done; one by
the same name at another size is left alone and Daf is told why.

The downloads run in a background process, so a big one never holds up the screen. Each streams
straight into the shelf under a hidden name (.<name>.daf-part), stops past the size Daf gave (and
200 MB at most), is checked against that size, renamed, and reported done to Daf
(POST /api/kindle/inbox/<id>/done, with {error} when it couldn't be, which takes it off the list
until it's sent again; a broken connection is only reported on the third try in a row). When
they're over, the shelves and the file browser show the new books, their covers are made, and
one message says how many came.
]]
local FFIUtil = require("ffi/util")
local InfoMessage = require("ui/widget/infomessage")
local UIManager = require("ui/uimanager")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")
local time = require("ui/time")
local util = require("util")
local _ = require("gettext")
local C = require("canvas").C

local Inbox = {}
local MAX = 210 * 1024 * 1024     -- Daf sends 200 MB at most
local ROOM = 50 * 1024 * 1024     -- what a download leaves free on the Kindle, at least
local job

-- One file or folder name, safe on the Kindle's storage; nil for nothing, or a hidden name.
local function clean(s)
    s = tostring(s or ""):gsub('[\\/:*?"<>|%c]', " "):gsub("^%s+", ""):gsub("%s+$", "")
    if s == "" or s:sub(1, 1) == "." then return nil end
    return s
end

-- A shelf, perhaps one inside another ("Books/Sci-fi"), each part safe; nil for none.
local function shelfPath(s)
    local parts = {}
    for p in tostring(s or ""):gmatch("[^/]+") do
        local c = clean(p)
        if c then table.insert(parts, c) end
    end
    return #parts > 0 and table.concat(parts, "/") or nil
end

-- Ids have ":" and spaces in them.
local function enc(id)
    return (tostring(id):gsub("[^%w%-_.~]", function(ch) return string.format("%%%02X", ch:byte()) end))
end

-- The folders in the home folder.
local function shelves(home)
    local out = {}
    for f in lfs.dir(home) do
        if f:sub(1, 1) ~= "." and not f:match("%.sdr$") and lfs.attributes(home .. "/" .. f, "mode") == "directory" then
            table.insert(out, f)
        end
    end
    table.sort(out)
    return out
end

-- Every book on the shelves (four deep) and in the home folder: {path from home, md5}. The
-- fingerprints are kept in settings/daf_files.lua by size and time, so only new books are read.
local function books(home)
    local LuaSettings = require("luasettings")
    local DataStorage = require("datastorage")
    local cache = LuaSettings:open(DataStorage:getSettingsDir() .. "/daf_files.lua")
    local known, now, out = cache:readSetting("files") or {}, {}, {}
    local function walk(dir, rel, depth)
        for f in lfs.dir(dir) do
            if f:sub(1, 1) ~= "." and not f:match("%.sdr$") then
                local full, path = dir .. "/" .. f, rel == "" and f or rel .. "/" .. f
                local a = lfs.attributes(full)
                if a and a.mode == "directory" and depth < 4 then
                    walk(full, path, depth + 1)
                elseif a and a.mode == "file" and C.BOOK_EXT[(f:match("%.([^.]+)$") or ""):lower()] then
                    local k, md5 = known[path]
                    if k and k.size == a.size and k.time == a.modification then md5 = k.md5
                    else md5 = util.partialMD5(full) end
                    now[path] = { size = a.size, time = a.modification, md5 = md5 }
                    table.insert(out, { path = path, md5 = md5 })
                end
            end
        end
    end
    pcall(walk, home, "", 1)
    cache:saveSetting("files", now)
    cache:flush()
    return out
end

-- A book to another shelf (dest "" is the home folder), as Move to shelf… moves it: its notes
-- (.sdr), its place in the history and its collections go with it. Returns its new path from
-- home, or nil and what went wrong.
local function moveBook(home, mv)
    local src, dest_dir = home .. "/" .. tostring(mv.path or ""), home
    if mv.dest and mv.dest ~= "" then
        local d = shelfPath(mv.dest)
        if not d then return nil, "Not a shelf the Kindle can make" end
        dest_dir = home .. "/" .. d
    end
    if tostring(mv.path or ""):find("..", 1, true) or lfs.attributes(src, "mode") ~= "file" then return nil, "It isn't there on the Kindle any more" end
    local reader = require("apps/reader/readerui").instance
    if reader and reader.document and reader.document.file == src then return nil, "It's open on the Kindle" end
    if not util.makePath(dest_dir) then return nil, "Couldn't make the shelf on the Kindle" end
    local dest = dest_dir .. "/" .. src:match("([^/]+)$")
    if dest == src then return dest:sub(#home + 2) end
    if lfs.attributes(dest, "mode") then return nil, "There's a book by that name on that shelf" end
    local ok, err = os.rename(src, dest)
    if not ok then return nil, "Couldn't move it (" .. tostring(err) .. ")" end
    pcall(function() require("docsettings").updateLocation(src, dest) end)
    pcall(function() require("readhistory"):updateItem(src, dest) end)
    pcall(function() require("readcollection"):updateItem(src, dest) end)
    return dest:sub(#home + 2)
end

-- ---------------------------------------------------------------- in the background process

-- One file into its shelf. Returns what went wrong, or nil; and true when it was the connection
-- (worth trying again) rather than the file.
local function download(it, url, token)
    local http = require("socket.http")
    local socketutil = require("socketutil")
    local dir = it.dest:match("^(.*)/[^/]+$")
    if not util.makePath(dir) then return "Couldn't make the shelf on the Kindle" end
    local tmp = dir .. "/." .. it.dest:match("([^/]+)$") .. ".daf-part"
    local fh = io.open(tmp, "wb")
    if not fh then return "Couldn't write on the Kindle" end
    local got, limit = 0, math.min(MAX, it.size or MAX)
    local too_big
    local function sink(chunk)
        if not chunk then return 1 end
        got = got + #chunk
        if got > limit then
            too_big = true
            return nil, "too big"
        end
        return fh:write(chunk)
    end
    socketutil:set_timeout(30, 3600)
    local ok, code = http.request{
        url = url .. "/api/kindle/inbox/" .. it.q .. "/file",
        headers = { ["Authorization"] = "Bearer " .. token },
        sink = sink,
    }
    socketutil:reset_timeout()
    pcall(fh.close, fh)
    local err, again
    if too_big then err = "The file was bigger than Daf said"
    elseif not ok then err, again = "The download stopped (" .. tostring(code) .. ")", true
    elseif code ~= 200 then err, again = "Daf answered " .. tostring(code), true
    elseif it.size and lfs.attributes(tmp, "size") ~= it.size then err, again = "The file came in short", true
    elseif not os.rename(tmp, it.dest) then err = "Couldn't put it on the shelf" end
    if err then os.remove(tmp) end
    return err, again
end

-- Daf drops a file it's told about, until it's sent again; so a broken connection isn't told,
-- and the file comes again on the next sync, until its third try in a row (it.last).
local function fetchAll(todo, url, token, request)
    for _i, it in ipairs(todo) do
        local ok, err, again = pcall(download, it, url, token)
        if not ok then err, again = "Something went wrong: " .. tostring(err), false end
        if not (err and again and not it.last) then
            request("POST", url .. "/api/kindle/inbox/" .. it.q .. "/done", token, err and { error = err } or {})
        end
    end
end

-- ---------------------------------------------------------------- in KOReader

-- The new books show, get their covers, and one message says how many came.
local function landed(daf, n)
    pcall(function()
        local fm = require("apps/filemanager/filemanager").instance
        if fm and fm.file_chooser then fm.file_chooser:refreshPath() end
        C.refreshShown()
    end)
    pcall(function() daf:coversAhead() end)
    UIManager:show(InfoMessage:new{
        text = n == 1 and _("Daf put a book on your Kindle.") or string.format(_("Daf put %d books on your Kindle."), n),
        timeout = 4,
    })
end

local function start(daf, todo, url, token, request)
    local pid = FFIUtil.runInSubProcess(function() fetchAll(todo, url, token, request) end)
    if not pid then
        logger.warn("[Daf] inbox: couldn't start the background process")
        return
    end
    UIManager:preventStandby()
    job = { pid = pid, todo = todo, started = time.now() }
    local function watch()
        if not FFIUtil.isSubProcessDone(job.pid) then
            if time.since(job.started) > time.s(3600) then FFIUtil.terminateSubProcess(job.pid) end
            return UIManager:scheduleIn(1, watch)
        end
        UIManager:allowStandby()
        local came = 0
        local tries = daf.settings:readSetting("inbox_tries") or {}
        for _i, it in ipairs(job.todo) do
            local size = lfs.attributes(it.dest, "size")
            if size and (not it.size or size == it.size) then
                came = came + 1
                tries[it.id] = nil
            else
                tries[it.id] = (tries[it.id] or 0) + 1
            end
        end
        daf.settings:saveSetting("inbox_tries", tries)
        daf.settings:flush()
        logger.info(string.format("[Daf] inbox: %d of %d files came in %.0f s", came, #job.todo, time.to_s(time.since(job.started))))
        job = nil
        if came > 0 then landed(daf, came) end
    end
    UIManager:scheduleIn(1, watch)
end

-- On the Wi-Fi sync. request is main.lua's: (method, url, token, body) → Daf's answer, or nil.
function Inbox.sync(daf, request)
    if job then return end
    local url, token = daf.settings:readSetting("url"), daf.settings:readSetting("token")
    local home = C.homeDir()
    if not (url and token) or lfs.attributes(home, "mode") ~= "directory" then return end
    local rep = request("POST", url .. "/api/kindle/shelves", token, { shelves = shelves(home), files = books(home) })
    local moved = 0
    for _i, mv in ipairs(rep and type(rep.moves) == "table" and rep.moves or {}) do
        if mv.id then
            local path, err = moveBook(home, mv)
            if path then moved = moved + 1 end
            request("POST", url .. "/api/kindle/moves/" .. enc(mv.id) .. "/done", token, err and { error = err } or { path = path })
            logger.info("[Daf] shelves: " .. tostring(mv.path) .. " → " .. tostring(mv.dest) .. (err and (": " .. err) or ""))
        end
    end
    if moved > 0 then
        pcall(function()
            local fm = require("apps/filemanager/filemanager").instance
            if fm and fm.file_chooser then fm.file_chooser:refreshPath() end
            C.refreshShown()
        end)
    end
    local res = request("GET", url .. "/api/kindle/inbox", token)
    local files = res and res.files
    if type(files) ~= "table" or #files == 0 then return end
    local free = (util.diskUsage(home) or {}).available
    -- how many times in a row each one didn't come (only those still waiting)
    local was, tries = daf.settings:readSetting("inbox_tries") or {}, {}
    for _i, f in ipairs(files) do
        if f.id and was[f.id] then tries[f.id] = was[f.id] end
    end
    daf.settings:saveSetting("inbox_tries", tries)
    local todo = {}
    for _i, f in ipairs(files) do
        local name, shelf, size = clean(f.name), shelfPath(f.shelf) or "Books", tonumber(f.size)
        local q = f.id and enc(f.id)
        local function done(err)
            request("POST", url .. "/api/kindle/inbox/" .. q .. "/done", token, err and { error = err } or {})
        end
        if not q then
            logger.warn("[Daf] inbox: an item with no id")
        elseif not name then
            done("It came with no file name")
        elseif not C.BOOK_EXT[(name:match("%.([^.]+)$") or ""):lower()] then
            done("The Kindle doesn't keep this kind of file")
        elseif size and size > MAX then
            done("Too big for the Kindle (over 200 MB)")
        else
            local dest = home .. "/" .. shelf .. "/" .. name
            local have = lfs.attributes(dest, "size")
            if have and have == size then
                done()
            elseif have then
                done("There's already a different file by that name on the Kindle")
            elseif free and size and free - size < ROOM then
                done("There isn't room for it on the Kindle")
            else
                if free and size then free = free - size end
                table.insert(todo, { id = f.id, q = q, dest = dest, size = size, last = (tries[f.id] or 0) >= 2 })
            end
        end
    end
    if #todo > 0 then start(daf, todo, url, token, request) end
end

-- For the simulator: is a download under way?
function Inbox.busy()
    return job ~= nil
end

return Inbox
