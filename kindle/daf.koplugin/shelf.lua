--[[
A shelf: one folder of the library, as covers. Shelves in the bar opens the home folder (Libros):
its folders as tiles with their drawings. A folder opens as its books, three across and two down,
a page at a time (swipe, or ‹ ›), with its own folders first, so a shelf inside a shelf opens the
same way. At the top: back (to the folder above, or Home from the top), the folder's drawing,
name and count, Files, and the order (Newest, Title, Author, Last read; tap to change). Under it:
All, Reading, New, Finished.

Tap a book to open it. Hold a book or a shelf for KOReader's own dialog, as in its file browser:
Cut, Copy, Paste, Rename, Delete, Select, the book's status, collections, Book information, and
Daf's Move to shelf…, a list of every shelf to send it to. After Cut or Copy, every shelf shows
a bar to put it there. Files has New shelf here, Select several (in KOReader's browser, which
has the tools for many at once) and the browser itself at this folder.

A book on Daf's private list shows as its file name only, with no cover. Covers the screen
doesn't have yet come in one at a time after it's drawn, so a new folder opens at once.
]]
local ButtonDialog = require("ui/widget/buttondialog")
local Device = require("device")
local InfoMessage = require("ui/widget/infomessage")
local InputDialog = require("ui/widget/inputdialog")
local UIManager = require("ui/uimanager")
local util = require("util")
local lfs = require("libs/libkoreader-lfs")
local _ = require("gettext")
local Canvas = require("canvas")
local C = Canvas.C
local px, SERIF, SANS, MID, SOFT, WHITE = C.px, C.SERIF, C.SANS, C.MID, C.SOFT, C.WHITE

local SORTS = { { "new", _("Newest first") }, { "title", _("Title") }, { "author", _("Author") }, { "read", _("Last read") } }
local FILTERS = { { "all", _("All") }, { "reading", _("Reading") }, { "new", _("New") }, { "finished", _("Finished") } }

local Shelf = Canvas:extend{
    name = "daf_shelf",
    path = nil,
}

function Shelf:init()
    local st = self.daf.settings:readSetting("shelf_view") or {}
    self.sort = st.sort or "new"
    self.filter = "all"
    self.page = 1
    self:load()
    Canvas.init(self)
end

-- The folder's own folders and books.
function Shelf:load()
    self.folders = C.folders(self.path)
    self.books = {}
    local private = self:privateMd5s()
    local ok, iter, obj = pcall(lfs.dir, self.path)
    if ok then
        for f in iter, obj do
            local p = self.path .. "/" .. f
            if f:sub(1, 1) ~= "." and lfs.attributes(p, "mode") == "file" and C.BOOK_EXT[(f:match("%.([^.]+)$") or ""):lower()] then
                local b = C.bookInfo(p)
                if b.md5 and private[b.md5] then
                    b.private, b.title, b.author = true, f:gsub("%.[^.]+$", ""), nil
                end
                table.insert(self.books, b)
            end
        end
    end
    self.count = C.bookCount(self.path, 0)
end

function Shelf:status(b)
    if b.finished then return "finished" end
    if b.pct and b.pct > 0 then return "reading" end
    return "new"
end

function Shelf:entries()
    local list = {}
    if self.filter == "all" then
        for _i, f in ipairs(self.folders) do table.insert(list, f) end
    end
    local books = {}
    for _i, b in ipairs(self.books) do
        if self.filter == "all" or self:status(b) == self.filter then table.insert(books, b) end
    end
    local key = self.sort
    table.sort(books, function(a, b)
        if key == "title" then return (a.title or ""):lower() < (b.title or ""):lower() end
        if key == "author" then
            local x, y = (a.author or "~"):lower(), (b.author or "~"):lower()
            if x ~= y then return x < y end
            return (a.title or ""):lower() < (b.title or ""):lower()
        end
        if key == "read" then return (a.read or 0) > (b.read or 0) end
        return (a.mtime or 0) > (b.mtime or 0)
    end)
    for _i, b in ipairs(books) do table.insert(list, b) end
    return list
end

function Shelf:isRoot()
    return self.path == C.homeDir()
end

function Shelf:layout()
    self.ops, self.taps, self.missing = {}, {}, {}
    local W = self.dimen.w
    local L, R = px(56), W - px(56)
    local inner = R - L
    local y = self:statusLine()
    local nav_top = self:navBar(self:isRoot() and "shelves" or nil)

    -- back, the folder, its count, the order
    y = y + px(26)
    local name = self.path:match("([^/]+)$") or self.path
    local x = L
    self:text("‹", SERIF, 64, x, y - px(6))
    self:tap(0, y - px(20), px(120), px(110), function() self:back() end)
    x = x + px(56)
    local icon = C.folderIcon(self.path)
    if icon and not self:isRoot() then
        self:image(icon, x, y, px(76), px(76), false)
        x = x + px(96)
    end
    self:text(self:isRoot() and _("Shelves") or name, SERIF, 58, x, y - px(4), { bold = true, max_w = px(560) })
    local n = self:isRoot() and #self.folders or self.count
    self:text(self:isRoot() and string.format(_("%d shelves · %d books"), #self.folders, self.count)
              or string.format(n == 1 and _("%d book") or _("%d books"), n), SANS, 24, x, y + px(66), { color = MID })
    -- right: Files, and the order when there are books
    local rx = R
    local fw = px(140)
    self:pill(rx - fw, y + px(4), fw, px(58), false)
    self:text(_("Files") .. "  ▾", SANS, 23, rx - math.floor(fw / 2), y + px(18), { align = "center" })
    self:tap(rx - fw, y, fw, px(70), function() self:filesMenu() end)
    rx = rx - fw - px(16)
    if #self.books > 1 then
        local label = SORTS[1][2]
        for _i, s in ipairs(SORTS) do if s[1] == self.sort then label = s[2] end end
        local sw = px(250)
        self:pill(rx - sw, y + px(4), sw, px(58), false)
        self:text(label .. "  ▾", SANS, 23, rx - math.floor(sw / 2), y + px(18), { align = "center" })
        self:tap(rx - sw, y, sw, px(70), function() self:nextSort() end)
    end
    y = y + px(112)

    -- after Cut or Copy: put it here
    local clip, cut = self:clipboard()
    if clip then
        local h = px(64)
        self:frame(L, y - px(4), inner, h + px(8), px(2), px(14))
        local what = clip:match("([^/]+)$") or clip
        if lfs.attributes(clip, "mode") == "file" then what = C.shortTitle(C.bookInfo(clip).title or what) end
        local bw1, bw2 = px(220), px(150)
        self:text((cut and _("Moving: ") or _("Copying: ")) .. what, SANS, 24, L + px(22), y + px(16),
                  { bold = true, max_w = inner - bw1 - bw2 - px(70) })
        local bx = R - px(8) - bw1
        self:pill(bx, y + px(4), bw1, h - px(8), true)
        self:text(_("Put it here"), SANS, 23, bx + math.floor(bw1 / 2), y + px(17), { align = "center", bold = true, color = WHITE })
        self:tap(bx, y - px(4), bw1, h + px(8), function() self:pasteHere() end)
        bx = bx - px(12) - bw2
        self:pill(bx, y + px(4), bw2, h - px(8), false)
        self:text(_("Cancel"), SANS, 23, bx + math.floor(bw2 / 2), y + px(17), { align = "center" })
        self:tap(bx, y - px(4), bw2, h + px(8), function() self:clearClipboard() end)
        y = y + h + px(24)
    end

    -- All, Reading, New, Finished
    if #self.books > 0 then
        local cx = L
        for _i, f in ipairs(FILTERS) do
            local on = self.filter == f[1]
            local w = math.max(px(96), self:measure(f[2], SANS, 24, on) + px(48))
            self:pill(cx, y, w, px(56), on)
            self:text(f[2], SANS, 24, cx + math.floor(w / 2), y + px(14), { align = "center", bold = on, color = on and WHITE or nil })
            local key = f[1]
            self:tap(cx, y, w, px(56), function() self.filter = key; self.page = 1; self:update() end)
            cx = cx + w + px(14)
        end
        y = y + px(80)
    end

    -- the grid: books three across and two down; shelves alone four across and three down
    local entries = self:entries()
    local folders_only = #self.books == 0
    local cols, rows = 3, 2
    if folders_only then cols, rows = 3, math.max(2, math.min(4, math.ceil(#entries / 3))) end
    local per = cols * rows
    local pages = math.max(1, math.ceil(#entries / per))
    if self.page > pages then self.page = pages end
    local pager_h = px(64)
    local gap_x, gap_y = px(40), px(26)
    local colw = math.floor((inner - (cols - 1) * gap_x) / cols)
    local cell_h = math.floor((nav_top - pager_h - px(10) - y - (rows - 1) * gap_y) / rows)
    local text_h = px(96)
    local cover_h = math.min(cell_h - text_h, math.floor(colw * 1.5))
    local cover_w = math.min(colw, math.floor(cover_h / 1.5))
    self.grid = { cover_w = cover_w, cover_h = cover_h }
    for i = 1, per do
        local e = entries[(self.page - 1) * per + i]
        if not e then break end
        local col, row = (i - 1) % cols, math.floor((i - 1) / cols)
        local cx = L + col * (colw + gap_x)
        local cy = y + row * (cell_h + gap_y)
        if e.folder then
            self:frame(cx, cy, colw, cell_h - px(10), px(2), px(12))
            local ic = math.min(colw - px(60), cell_h - px(150))
            if e.icon then self:image(e.icon, cx + math.floor((colw - ic) / 2), cy + px(24), ic, ic, false) end
            self:text(e.name, SERIF, 30, cx + math.floor(colw / 2), cy + px(24) + ic + px(10), { align = "center", bold = true, max_w = colw - px(20) })
            self:text(e.n == 0 and _("empty") or string.format(e.n == 1 and _("%d book") or _("%d books"), e.n), SANS, 22,
                      cx + math.floor(colw / 2), cy + px(24) + ic + px(54), { align = "center", color = MID })
            local path = e.path
            self:tap(cx, cy, colw, cell_h, function() self:openShelf(path) end, function() self:fileDialog(path, false) end)
        else
            local bx = cx + math.floor((colw - cover_w) / 2)
            local made
            if e.private then
                self:frame(bx, cy, cover_w, cover_h)
                made = true
            else
                made = self:coverOrTitle(e, bx, cy, cover_w, cover_h, false)
            end
            if not made then table.insert(self.missing, { book = e, x = bx, y = cy }) end
            local ty = cy + cover_h + px(10)
            local th = self:box(C.shortTitle(e.title), SERIF, 25, cx, ty, colw, 2, { bold = true })
            local st = self:status(e)
            local sy = ty + th + px(6)
            if st == "reading" then
                self:bar(cx, sy + px(8), px(90), px(12), e.pct)
                self:text(string.format("%d%%", math.floor(e.pct * 100 + 0.5)) .. (e.author and (" · " .. e.author) or ""), SANS, 21, cx + px(104), sy, { color = MID, max_w = colw - px(104) })
            elseif st == "finished" then
                self:text("✓ " .. _("Finished") .. (e.author and (" · " .. e.author) or ""), SANS, 21, cx, sy, { color = MID, max_w = colw })
            else
                self:dot(cx + px(8), sy + px(14), px(7))
                self:text(_("New") .. (e.author and (" · " .. e.author) or ""), SANS, 21, cx + px(24), sy, { color = MID, max_w = colw - px(24) })
            end
            local file = e.file
            self:tap(cx, cy, colw, cell_h, function() self:openBook(file) end, function() self:fileDialog(file, true) end)
        end
    end
    if #entries == 0 then
        self:box(self.filter == "all" and _("Nothing on this shelf yet.") or _("Nothing here with that filter."), SERIF, 30, L, y + px(60), inner, 2, { align = "center", color = MID })
    end

    -- ‹ 1 of 5 ›
    if pages > 1 then
        local py = nav_top - pager_h
        local mid = math.floor(W / 2)
        self:text("‹", SERIF, 46, mid - px(150), py + px(2), { align = "center" })
        self:text(string.format(_("%d of %d"), self.page, pages), SANS, 24, mid, py + px(14), { align = "center" })
        self:text("›", SERIF, 46, mid + px(150), py + px(2), { align = "center" })
        self:tap(mid - px(260), py, px(200), pager_h, function() self:turn(-1) end)
        self:tap(mid + px(60), py, px(200), pager_h, function() self:turn(1) end)
    end
    self.pages = pages
end

-- Covers the screen doesn't have yet, one after another once it's up.
function Shelf:fillCovers()
    UIManager:unschedule(self.fill_fn)
    self.fill_fn = self.fill_fn or function()
        if not UIManager:isWidgetShown(self) then return end
        local m = table.remove(self.missing or {}, 1)
        if not m then return end
        C.cover(m.book, self.grid.cover_w, self.grid.cover_h, true)
        self:update(require("ui/geometry"):new{ x = m.x, y = m.y, w = self.grid.cover_w, h = self.grid.cover_h })
        if #self.missing > 0 then UIManager:scheduleIn(0.05, self.fill_fn) end
    end
    if self.missing and #self.missing > 0 then UIManager:scheduleIn(0.3, self.fill_fn) end
end

function Shelf:update(region)
    Canvas.update(self, region)
    if not region then self:fillCovers() end
end

function Shelf:onShow()
    Canvas.onShow(self)
    self:fillCovers()
end

function Shelf:onCloseWidget()
    Canvas.onCloseWidget(self)
    if self.fill_fn then UIManager:unschedule(self.fill_fn) end
end

function Shelf:onPageSwipe(ges)
    if ges.direction == "west" then self:turn(1)
    elseif ges.direction == "east" then self:turn(-1) end
    return true
end

function Shelf:turn(d)
    local p = self.page + d
    if p >= 1 and p <= (self.pages or 1) then self.page = p; self:update() end
end

function Shelf:nextSort()
    for i, s in ipairs(SORTS) do
        if s[1] == self.sort then self.sort = SORTS[i % #SORTS + 1][1]; break end
    end
    self.daf.settings:saveSetting("shelf_view", { sort = self.sort })
    self.daf.settings:flush()
    self.page = 1
    self:update()
end

function Shelf:back()
    if self:isRoot() then return self:goHomeScreen() end
    local up = self.path:match("^(.*)/[^/]+$")
    local home = C.homeDir()
    if not up or #up < #home then return self:goHomeScreen() end
    self:openShelf(up)
end

-- ---------------------------------------------------------------- files

-- KOReader's own dialog for a book or a folder, the one its file browser opens on a long-press
-- (Project: Title's when that's in). The browser under the shelf goes to this folder first, so
-- Select and Paste there agree with what's on the screen. Over a book (no browser), a book's
-- information.
function Shelf:fileDialog(path, is_file)
    local fm = self:fm()
    local fc = fm and fm.file_chooser
    if not (fc and fc.showFileDialog) then
        local ui = self:ui()
        if is_file and ui and ui.bookinfo then pcall(function() ui.bookinfo:show(path) end) end
        return
    end
    if fc.path ~= self.path then
        C.quiet = C.quiet + 1
        pcall(function() fc:changeToPath(self.path) end)
        C.quiet = C.quiet - 1
    end
    C.expecting = true
    fc:showFileDialog({ path = path, is_file = is_file, text = path:match("([^/]+)$") })
end

function Shelf:clipboard()
    local fm = self:fm()
    if fm and fm.clipboard then return fm.clipboard, fm.cutfile end
end

function Shelf:pasteHere()
    local fm = self:fm()
    if not (fm and fm.clipboard) then return end
    C.expecting = true
    fm:pasteFileFromClipboard(self.path)
    self:load()
    self:update()
end

function Shelf:clearClipboard()
    local fm = self:fm()
    if fm then fm.clipboard = nil end
    self:update()
end

-- Files ▾: a new shelf here, several books at once in KOReader's browser, or the browser.
function Shelf:filesMenu()
    local dialog
    local fm = self:fm()
    dialog = ButtonDialog:new{
        title = self:isRoot() and _("Shelves") or (self.path:match("([^/]+)$") or self.path),
        title_align = "center",
        buttons = {
            { { text = _("New shelf here…"), callback = function() UIManager:close(dialog); self:newShelf() end } },
            { { text = _("Select several…"), enabled = fm ~= nil, callback = function()
                UIManager:close(dialog)
                self:fileBrowser(self.path)
                local now = self:fm()
                if now and not now.selected_files then now:onToggleSelectMode() end
            end } },
            { { text = _("Open in the file browser"), callback = function() UIManager:close(dialog); self:fileBrowser(self.path) end } },
        },
    }
    UIManager:show(dialog)
end

function Shelf:newShelf()
    local input
    input = InputDialog:new{
        title = _("New shelf"),
        input_hint = _("Name"),
        buttons = { {
            { text = _("Cancel"), id = "close", callback = function() UIManager:close(input) end },
            { text = _("Make it"), is_enter_default = true, callback = function()
                local name = util.trim(input:getInputText() or "")
                if name == "" or name:find("/", 1, true) then return end
                UIManager:close(input)
                if util.makePath(self.path .. "/" .. name) then
                    self:load()
                    self:update()
                else
                    UIManager:show(InfoMessage:new{ text = _("Couldn't make that shelf."), icon = "notice-warning" })
                end
            end },
        } },
    }
    UIManager:show(input)
    input:onShowKeyboard()
end

-- Move to shelf…: every shelf, three deep, as a list; the book (or folder) goes where you tap,
-- with KOReader's own Cut and Paste (its notes, history and collections move with it).
function Shelf.pickShelf(file, is_file)
    local fm = require("apps/filemanager/filemanager").instance
    if not fm then return end
    local here = file:match("^(.*)/[^/]+$")
    local home = C.homeDir()
    local items = {}
    if here ~= home then table.insert(items, { text = home:match("([^/]+)$") or home, path = home }) end
    for _i, f in ipairs(C.allFolders(not is_file and file or nil)) do
        if f.path ~= here then
            table.insert(items, { text = string.rep("\226\128\131\226\128\131", f.depth - 1) .. f.name, path = f.path })
        end
    end
    if #items == 0 then
        UIManager:show(InfoMessage:new{ text = _("There's no other shelf to move it to."), timeout = 3 })
        return
    end
    local name = file:match("([^/]+)$") or file
    if is_file then name = C.shortTitle(C.bookInfo(file).title or name) end
    local dialog
    local buttons = {}
    for _i, it in ipairs(items) do
        local dest = it.path
        table.insert(buttons, { {
            text = it.text,
            align = "left",
            callback = function()
                UIManager:close(dialog)
                C.expecting = true
                fm:cutFile(file)
                fm:pasteFileFromClipboard(dest)
            end,
        } })
    end
    dialog = ButtonDialog:new{
        title = string.format(_("Move “%s” to"), name),
        title_align = "center",
        buttons = buttons,
        rows_per_page = 9,
    }
    UIManager:show(dialog)
end

function Shelf:onClose()
    self:back()
    return true
end

return Shelf
