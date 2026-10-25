--[[
Books from Daf: what Daf has waiting for the Kindle (a book put on the Kindle from Daf, Send to
Kindle's articles), brought in on the Wi-Fi sync, since Syncthing is off on the Kindle.

On each sync (not the one as the Kindle goes to sleep), the Kindle tells Daf its shelves (the
folders in the home folder: POST /api/kindle/shelves) and asks what's waiting (GET
/api/kindle/inbox, oldest first). Each file goes into its shelf, <home>/<shelf>/<name>, and the
shelf is made if it isn't there. One already there at the same size is only marked done; one by
the same name at another size is left alone and Daf is told why.

The downloads run in a background process, so a big one never holds up the screen. Each streams
straight into the shelf under a hidden name (.<name>.daf-part), stops past the size Daf gave (and
200 MB at most), is checked against that size, renamed, and reported done to Daf
(POST /api/kindle/inbox/<id>/done, with {error} when it couldn't be). When they're over, the
shelves and the file browser show the new books, their covers are made, and one message says how
many came.
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

-- ---------------------------------------------------------------- in the background process

-- One file into its shelf. Returns what went wrong, or nil.
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
    local err
    if too_big then err = "The file was bigger than Daf said"
    elseif not ok then err = "The download stopped (" .. tostring(code) .. ")"
    elseif code ~= 200 then err = "Daf answered " .. tostring(code)
    elseif it.size and lfs.attributes(tmp, "size") ~= it.size then err = "The file came in short"
    elseif not os.rename(tmp, it.dest) then err = "Couldn't put it on the shelf" end
    if err then os.remove(tmp) end
    return err
end

local function fetchAll(todo, url, token, request)
    for _i, it in ipairs(todo) do
        local ok, err = pcall(download, it, url, token)
        if not ok then err = "Something went wrong: " .. tostring(err) end
        request("POST", url .. "/api/kindle/inbox/" .. it.q .. "/done", token, err and { error = err } or {})
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
        for _i, it in ipairs(job.todo) do
            local size = lfs.attributes(it.dest, "size")
            if size and (not it.size or size == it.size) then came = came + 1 end
        end
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
    request("POST", url .. "/api/kindle/shelves", token, { shelves = shelves(home) })
    local res = request("GET", url .. "/api/kindle/inbox", token)
    local files = res and res.files
    if type(files) ~= "table" or #files == 0 then return end
    local free = (util.diskUsage(home) or {}).available
    local todo = {}
    for _i, f in ipairs(files) do
        local name, shelf, size = clean(f.name), clean(f.shelf) or "Books", tonumber(f.size)
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
                table.insert(todo, { q = q, dest = dest, size = size })
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
