--[[
Book covers for Home and the shelves.

Each size a screen shows is kept as a small gray JPEG in cache/daf-home, named by the book's
partial md5 (KOReader's own id for a book, so a cover follows its book to another shelf):
<md5>_<w>x<h>.jpg. A size that isn't there yet is cut from the first of these that has the cover:

  1. a cover set by hand in Book information (KOReader keeps it with the book's notes);
  2. the book's master, <md5>.jpg, one cover about 600 px tall, kept when the book had to be opened;
  3. Project: Title's saved covers (settings/PT_bookinfo_cache.sqlite3, up to 600×600), then
     KOReader's cover browser's (settings/bookinfo_cache.sqlite3) when it's big enough; read only;
  4. the book itself. Opening a book is slow on the Kindle (crengine for EPUB, MuPDF for CBZ and
     PDF, worst for manga), so a screen never waits for it: those books are opened one after
     another in a background process, which keeps the master, so a book is opened once at most.

1–3 take about 30 ms on the Kindle. <md5>.none says a book has no cover.

After Home comes up, a pass goes over the whole library a few books at a time, between taps,
making the shelf-size cover of every book and sending the ones that need opening to the
background process. A shelf has the next page's covers made while one is showing. Books on
Daf's private list never get a cover, and any they had is deleted.
]]
local Blitbuffer = require("ffi/blitbuffer")
local DataStorage = require("datastorage")
local Device = require("device")
local DocSettings = require("docsettings")
local FFIUtil = require("ffi/util")
local UIManager = require("ui/uimanager")
local ffi = require("ffi")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")
local time = require("ui/time")
local util = require("util")

local Covers = {}
local CACHE = DataStorage:getDataDir() .. "/cache/daf-home"
local CR3_TMP = DataStorage:getDataDir() .. "/cache/daf-covers-cr3"
local PT_DB = DataStorage:getSettingsDir() .. "/PT_bookinfo_cache.sqlite3"
local CB_DB = DataStorage:getSettingsDir() .. "/bookinfo_cache.sqlite3"
local VERSION = ".v2"            -- the first version kept PNGs, some named by file name

local function exists(p) return lfs.attributes(p, "mode") == "file" end
local function touch(p) local f = io.open(p, "w"); if f then f:close() end end

local ready
local function prepare()
    if ready then return end
    ready = true
    lfs.mkdir(DataStorage:getDataDir() .. "/cache")
    lfs.mkdir(CACHE)
    if not exists(CACHE .. "/" .. VERSION) then
        local old = {}
        for f in lfs.dir(CACHE) do
            if f ~= "." and f ~= ".." then table.insert(old, f) end
        end
        for _i, f in ipairs(old) do os.remove(CACHE .. "/" .. f) end
        touch(CACHE .. "/" .. VERSION)
    end
end

local function sized(key, w, h) return string.format("%s/%s_%dx%d.jpg", CACHE, key, w, h) end

-- ---------------------------------------------------------------- which book

-- The partial md5 of each file, known by its size and time, kept between starts (keys.lua).
local keys, keys_dirty

local function saveKeys()
    if not (keys and keys_dirty) then return end
    keys_dirty = false
    local tmp = CACHE .. "/keys.lua.tmp"
    if util.writeToFile("return " .. require("dump")(keys) .. "\n", tmp) then os.rename(tmp, CACHE .. "/keys.lua") end
end

function Covers.key(file)
    if not keys then
        prepare()
        local ok, t = pcall(dofile, CACHE .. "/keys.lua")
        keys = ok and type(t) == "table" and t or {}
    end
    local attr = lfs.attributes(file)
    if not attr or attr.mode ~= "file" then return nil end
    local k = keys[file]
    if k and k[1] == attr.size and k[2] == attr.modification then return k[3] end
    local md5 = util.partialMD5(file)
    if md5 then
        keys[file] = { attr.size, attr.modification, md5 }
        keys_dirty = true
        UIManager:unschedule(saveKeys)
        UIManager:scheduleIn(5, saveKeys)
    end
    return md5
end

-- Daf's private books, as a set of md5s.
Covers.private = {}

-- What the book's notes file says its md5 is, when that's on the private list (a book changed
-- since it was first opened has another md5 than the file's).
local function privateByNotes(file)
    if not next(Covers.private) then return false end
    local sidecar = DocSettings:findSidecarFile(file)
    local text = sidecar and util.readFromFile(sidecar, "rb")
    local md5 = text and text:match('%["partial_md5_checksum"%]%s*=%s*"(%x+)"')
    return md5 ~= nil and Covers.private[md5] == true
end

-- ---------------------------------------------------------------- pictures

-- bb cut to fill w × h (its middle), gray. bb stays.
local function cut(bb, w, h)
    local bw, bh = bb:getWidth(), bb:getHeight()
    local s = math.max(w / bw, h / bh)
    local sw, sh = math.max(w, math.floor(bw * s + 0.5)), math.max(h, math.floor(bh * s + 0.5))
    local scaled = require("ui/renderimage"):scaleBlitBuffer(bb, sw, sh, false)
    local out = Blitbuffer.new(w, h, Blitbuffer.TYPE_BB8)
    out:blitFrom(scaled, 0, 0, math.floor((sw - w) / 2), math.floor((sh - h) / 2), w, h)
    if scaled ~= bb then scaled:free() end
    return out
end

-- A gray JPEG, written whole or not at all (a screen may be reading it).
local function writeJpeg(bb, path)
    local tmp = path .. ".tmp"
    local ok = pcall(function()
        local Jpeg = require("ffi/jpeg")
        Jpeg.encodeToFile(tmp, ffi.cast("uint8_t*", bb.data), bb:getWidth(), bb.stride, bb:getHeight(), 88,
                          ffi.C.TJPF_GRAY, ffi.C.TJSAMP_GRAY)
    end)
    if ok and exists(tmp) and os.rename(tmp, path) then return true end
    os.remove(tmp)
    return false
end

-- Every size asked for, from one picture.
local function writeSizes(bb, key, sizes)
    local first
    for _i, s in ipairs(sizes) do
        local out = cut(bb, s[1], s[2])
        local path = sized(key, s[1], s[2])
        if writeJpeg(out, path) then first = first or path end
        out:free()
    end
    return first
end

-- The master: at most this tall, the Home cover's height on this screen.
local function masterHeight()
    return math.floor(600 * Device.screen:getWidth() / 1236 + 0.5)
end

local function writeMaster(bb, key)
    local bw, bh = bb:getWidth(), bb:getHeight()
    local h = math.min(bh, masterHeight())
    local out = cut(bb, math.max(1, math.floor(bw * h / bh + 0.5)), h)
    local ok = writeJpeg(out, CACHE .. "/" .. key .. ".jpg")
    out:free()
    return ok
end

-- ---------------------------------------------------------------- the saved covers (3)

-- Open read only, and closed again after a few quiet seconds.
local dbs = {}
local function closeDbs()
    for _p, d in pairs(dbs) do
        if d then
            pcall(function() d.by_path:close(); d.by_name:close(); d.conn:close() end)
        end
    end
    dbs = {}
end

local COLS = "cover_w, cover_h, cover_bb_type, cover_bb_stride, cover_bb_data, cover_sizetag"
local function db(path)
    if dbs[path] == nil then
        dbs[path] = false
        if exists(path) then
            local ok, d = pcall(function()
                local conn = require("lua-ljsqlite3/init").open(path, "ro")
                conn:set_busy_timeout(1000)
                return {
                    conn = conn,
                    by_path = conn:prepare("SELECT " .. COLS .. " FROM bookinfo WHERE directory=? AND filename=? AND has_cover='Y'"),
                    by_name = conn:prepare("SELECT " .. COLS .. " FROM bookinfo WHERE filename=? AND has_cover='Y' LIMIT 2"),
                }
            end)
            if ok then dbs[path] = d else logger.warn("[Daf] covers: can't read", path, d) end
        end
    end
    UIManager:unschedule(closeDbs)
    UIManager:scheduleIn(8, closeDbs)
    return dbs[path] or nil
end

-- A row's picture, copied out (SQLite's pointer is only good until the next step).
local function decode(row)
    local w, h, bbtype, stride, blob = tonumber(row[1]), tonumber(row[2]), tonumber(row[3]), tonumber(row[4]), row[5]
    if not (w and h and bbtype and stride and blob) then return nil end
    local data, size = require("ffi/zstd").zstd_uncompress_ctx(blob[1], blob[2])
    if tonumber(size) ~= stride * h then
        ffi.C.free(data)
        return nil
    end
    local bb = Blitbuffer.new(w, h, bbtype, data, stride, w)
    bb:setAllocated(1)
    return bb, row[6]
end

-- The book's saved cover from one of the two: where it is now, or (moved since) the one book
-- by that file name.
local function fromDb(path, file)
    local d = db(path)
    if not d then return nil end
    local dir, name = util.splitFilePathName(file)
    local ok, bb, tag = pcall(function()
        local row = d.by_path:reset():bind(dir, name):step()
        if row then return decode(row) end
        row = d.by_name:reset():bind(name):step()
        if not row then return nil end
        local one, t = decode(row)
        if one and d.by_name:step() then
            one:free()
            return nil
        end
        return one, t
    end)
    pcall(function() d.by_path:reset(); d.by_name:reset() end)
    if ok then return bb, tag end
    logger.warn("[Daf] covers:", bb)
    closeDbs()
end

-- ---------------------------------------------------------------- where a cover comes from

-- The book's cover from 1–3, or nil. need_h: the height it's for (the cover browser keeps small ones).
local function quick(file, key, need_h)
    if DocSettings:findCustomCoverFile(file) then
        local ok, bb = pcall(function()
            local FBI = require("apps/filemanager/filemanagerbookinfo")
            return FBI:getCoverImage(nil, file)
        end)
        if ok and bb then return bb end
    end
    local master = CACHE .. "/" .. key .. ".jpg"
    if exists(master) then
        local ok, bb = pcall(function() return require("ui/renderimage"):renderImageFile(master, false) end)
        if ok and bb then return bb end
    end
    local bb = fromDb(PT_DB, file)
    if bb then return bb end
    local small, tag = fromDb(CB_DB, file)
    if small then
        local orig_h = tonumber(tag and tag:match("x(%d+)$"))
        if small:getHeight() >= need_h * 0.9 or (orig_h and orig_h <= small:getHeight()) then return small end
        small:free()
    end
end

-- ---------------------------------------------------------------- opening books, in the background

local queue, pending, job = {}, {}, nil

-- Who hears that covers came in (canvas.lua: the screens that are up), with the md5s.
Covers.on_ready = nil

-- In the background process: each book opened in turn, its sizes and master written. A book
-- that stopped the last process (.try still there) is taken as having no cover.
local function openAll(items)
    pcall(function()
        local cre = require("document/credocument"):engineInit()
        cre.initCache(CR3_TMP, 0, true, G_reader_settings:readSetting("cre_storage_size_factor") or 20)
    end)
    local FBI = require("apps/filemanager/filemanagerbookinfo")
    for _i, it in ipairs(items) do
        local base = CACHE .. "/" .. it.key
        if exists(base .. ".try") then
            touch(base .. ".none")
        else
            touch(base .. ".try")
            local ok, bb = pcall(FBI.getCoverImage, FBI, nil, it.file)
            if ok and bb then
                pcall(writeSizes, bb, it.key, it.sizes)
                local ok_m, wrote = pcall(writeMaster, bb, it.key)
                if not (ok_m and wrote) then touch(base .. ".none") end
                bb:free()
            else
                touch(base .. ".none")
            end
        end
        os.remove(base .. ".try")
    end
end

local startJob

local function watchJob()
    if not job then return end
    local landed = {}
    for i = #job.items, 1, -1 do
        local it = job.items[i]
        local base = CACHE .. "/" .. it.key
        if exists(base .. ".jpg") or exists(base .. ".none") then
            table.remove(job.items, i)
            pending[it.key] = nil
            table.insert(landed, it.key)
            job.last = time.now()
        end
    end
    local done = FFIUtil.isSubProcessDone(job.pid)
    if not done and time.since(job.last) > time.s(90) then
        logger.warn("[Daf] covers: a book took too long to open; stopping")
        FFIUtil.terminateSubProcess(job.pid)
    end
    if done then
        UIManager:allowStandby()
        -- what it didn't get to goes back in line
        for _i, it in ipairs(job.items) do
            it.tries = (it.tries or 0) + 1
            if it.tries < 3 then table.insert(queue, it) else pending[it.key] = nil end
        end
        logger.info(string.format("[Daf] covers: opened %d books in %.1f s", job.n, time.to_s(time.since(job.started))))
        job = nil
        pcall(FFIUtil.purgeDir, CR3_TMP)
        if #queue > 0 then UIManager:scheduleIn(0.5, startJob) end
    else
        UIManager:scheduleIn(0.5, watchJob)
    end
    if #landed > 0 and Covers.on_ready then pcall(Covers.on_ready, landed) end
end

startJob = function()
    if job or #queue == 0 then return end
    local items = {}
    while #queue > 0 and #items < 8 do table.insert(items, table.remove(queue, 1)) end
    closeDbs()           -- not shared with the other process
    local pid = FFIUtil.runInSubProcess(function() openAll(items) end)
    if not pid then
        logger.warn("[Daf] covers: couldn't start the background process")
        for _i, it in ipairs(items) do pending[it.key] = nil end
        return
    end
    UIManager:preventStandby()
    job = { pid = pid, items = items, n = #items, started = time.now(), last = time.now() }
    UIManager:scheduleIn(0.5, watchJob)
end

-- Sends a book to be opened; first in line when a screen is waiting for it.
local function open(file, key, sizes, first)
    local it = pending[key]
    if it then
        for _i, s in ipairs(sizes) do table.insert(it.sizes, s) end
        return
    end
    it = { file = file, key = key, sizes = { unpack(sizes) } }
    pending[key] = it
    table.insert(queue, first and 1 or #queue + 1, it)
    UIManager:unschedule(startJob)
    UIManager:scheduleIn(0.3, startJob)
end

-- ---------------------------------------------------------------- asking for a cover

--[[
The book's cover at w × h, as a file path. Made now from 1–3 unless only_kept; when it has to be
opened, it's sent to the background process. The second value says why there's none:
"later" (only_kept), "pending" (being opened; Covers.on_ready will say) or "none".
]]
function Covers.get(book, w, h, only_kept)
    local key = book.key or Covers.key(book.file)
    if not key then return nil, "none" end
    prepare()
    local path = sized(key, w, h)
    if exists(path) then return path end
    if pending[key] then return nil, "pending" end
    if exists(CACHE .. "/" .. key .. ".none") then return nil, "none" end
    if only_kept then return nil, "later" end
    local bb = quick(book.file, key, h)
    if bb then
        local made = writeSizes(bb, key, { { w, h } })
        bb:free()
        return made, made == nil and "none" or nil
    end
    open(book.file, key, { { w, h } }, true)
    return nil, "pending"
end

-- ---------------------------------------------------------------- filling the cache ahead

-- Books to make covers for, a few at a time between taps: { file, sizes }.
local ahead = {}

local function ahead1(it)
    local key = Covers.key(it.file)
    if not key or Covers.private[key] or pending[key] then return end
    local todo = {}
    for _i, s in ipairs(it.sizes) do
        if not exists(sized(key, s[1], s[2])) then table.insert(todo, s) end
    end
    if #todo == 0 or exists(CACHE .. "/" .. key .. ".none") or privateByNotes(it.file) then return end
    local bb = quick(it.file, key, todo[1][2])
    if bb then
        writeSizes(bb, key, todo)
        bb:free()
        return "made"
    end
    open(it.file, key, todo)
    return "opening"
end

-- What the pass over the library did, for the log.
local pass

local function step()
    -- never while a book is open: it looks again in a while
    if require("apps/reader/readerui").instance then
        UIManager:scheduleIn(20, step)
        return
    end
    local t0 = time.now()
    while #ahead > 0 do
        local ok, did = pcall(ahead1, table.remove(ahead, 1))
        if not ok then logger.warn("[Daf] covers:", did)
        elseif pass and did then pass[did] = pass[did] + 1 end
        if time.since(t0) > time.ms(30) then break end
    end
    if #ahead > 0 then
        UIManager:scheduleIn(0.2, step)
    else
        saveKeys()
        if pass then
            logger.info(string.format("[Daf] covers: library pass over %d books in %.1f s: %d made, %d to open",
                pass.books, time.to_s(time.since(pass.started)), pass.made, pass.opening))
            pass = nil
        end
    end
end

function Covers.resume(delay)
    if #ahead == 0 then return end
    UIManager:unschedule(step)
    UIManager:scheduleIn(delay or 0.2, step)
end

-- Make these books' covers at these sizes ahead of time; first: before the rest.
function Covers.ahead(files, sizes, first)
    for i, file in ipairs(files) do
        local it = { file = file, sizes = sizes }
        if first then table.insert(ahead, i, it) else table.insert(ahead, it) end
    end
    Covers.resume()
end

-- The pass over the whole library: every book's shelf-size cover. Private books' covers go.
function Covers.sweep(files, sizes, delay)
    prepare()
    if next(Covers.private) then
        local gone = {}
        for f in lfs.dir(CACHE) do
            local key = f:match("^(%x+)[_.]")
            if key and Covers.private[key] then table.insert(gone, f) end
        end
        for _i, f in ipairs(gone) do os.remove(CACHE .. "/" .. f) end
    end
    if keys then
        for file in pairs(keys) do
            if not exists(file) then keys[file] = nil; keys_dirty = true end
        end
    end
    ahead = {}
    for _i, file in ipairs(files) do table.insert(ahead, { file = file, sizes = sizes }) end
    pass = { books = #files, made = 0, opening = 0, started = time.now() }
    Covers.resume(delay)
end

-- For the simulator's timings: is anything still being made?
function Covers.busy()
    return #ahead > 0 or #queue > 0 or job ~= nil
end

return Covers
