--[[
The book's settings that aren't about the book, in KOReader's menu everywhere else too.

KOReader builds some of its settings only while a book is open: the status bar, page turns,
links, long-press on text, translation, fulltext search. They are global (they live in
settings.reader.lua and every book starts from them), so here they go into the file browser's
menu as well, which is also the menu Home and Shelves open: Settings → Status bar, Settings →
Taps and gestures → Page turns / Links / Long-press on text, Search → Settings.

Each is KOReader's own menu, built by its own reader module on a stand-in for a book: what the
items read and save is the real settings, and whatever would redraw an open book does
nothing. The next book that opens starts with them. Should one still fail, it says so and
KOReader carries on.
]]
local Device = require("device")
local UIManager = require("ui/uimanager")
local logger = require("logger")
local _ = require("gettext")

local M = {}

local function noop() end

-- Where they go in the file browser's menu, as in a book's (KOReader skips ids nobody provides).
local SEP = "----------------------------"

local function index(list, id)
    for i, v in ipairs(list) do if v == id then return i end end
end

-- Put `ids` before `before` (or at the end), once.
local function place(list, ids, before)
    if not list then return end
    for _i, id in ipairs(ids) do
        if id ~= SEP and index(list, id) then return end
    end
    local at = before and index(list, before) or #list + 1
    for i, id in ipairs(ids) do table.insert(list, at + i - 1, id) end
end

local placed = false
function M.placeInOrder()
    if placed then return end
    placed = true
    local order = require("ui/elements/filemanager_menu_order")
    place(order.setting, { SEP, "status_bar" })
    place(order.taps_and_gestures, { "follow_links", SEP }, "menu_activate")
    place(order.taps_and_gestures, { "page_turns", "long_press" })
    place(order.search_settings, { "translation_settings", SEP, "fulltext_search_settings" })
end

-- A stand-in for an open EPUB.
local function standIn()
    local view = {
        state = { page = 1 },
        footer_visible = true,
        flipping_visible = false,
        highlight = { disabled = G_reader_settings:readSetting("default_highlight_action") == "nothing" },
        inverse_reading_order = G_reader_settings:isTrue("inverse_reading_order"),
        setupTouchZones = noop,
        dialog = nil,
    }
    function view:onToggleReadingOrder()
        self.inverse_reading_order = not self.inverse_reading_order
        G_reader_settings:saveSetting("inverse_reading_order", self.inverse_reading_order)
    end
    local doc = {
        provider = "crengine",
        info = { has_pages = false },
        configurable = { h_page_margins = { 15, 15 }, b_page_margin = 15 },
    }
    local ui = { document = doc, view = view, rolling = true, handleEvent = noop }
    return ui, view
end

-- Every function in a menu item tree, run so that an error is a message, not a crash.
local function guard(items, seen)
    seen = seen or {}
    if type(items) ~= "table" or seen[items] then return items end
    seen[items] = true
    for k, v in pairs(items) do
        if type(v) == "function" and (k == "callback" or k == "hold_callback" or k:match("_func$")) then
            items[k] = function(...)
                local res = { pcall(v, ...) }
                if res[1] then return unpack(res, 2) end
                logger.warn("[Daf] reader setting:", res[2])
                if k == "callback" or k == "hold_callback" then
                    UIManager:show(require("ui/widget/infomessage"):new{
                        text = _("This one can only be changed with a book open."), timeout = 3,
                    })
                end
                if k == "text_func" then return "…" end
                if k == "enabled_func" then return false end
                return nil
            end
        elseif type(v) == "table" then
            guard(v, seen)
        end
    end
    return items
end

local function statusBar(menu_items)
    local ReaderFooter = require("apps/reader/modules/readerfooter")
    local ui, view = standIn()
    local footer = ReaderFooter:new{ ui = ui, view = view }
    for _i, name in ipairs({ "refreshFooter", "onUpdateFooter", "updateFooterPage", "updateFooterPos",
                             "updateFooterText", "_updateFooterText", "setTocMarkers", "resetLayout",
                             "rescheduleFooterAutoRefreshIfNeeded", "unscheduleFooterAutoRefresh" }) do
        footer[name] = noop
    end
    footer.getBookProgress = function() return 0.42 end
    footer.getChapterProgress = function(_self, get_percentage) return get_percentage and 0.3 or "3 ⁄ 10" end
    local out = {}
    footer:addToMainMenu(out)
    menu_items.status_bar = out.status_bar
end

local function pageTurns(menu_items)
    -- Its own file, loaded with a reader that's only the stand-in.
    local _ui, view = standIn()
    local chunk = assert(loadfile("frontend/ui/elements/page_turns.lua"))
    local env = setmetatable({
        require = function(name)
            if name == "apps/reader/readerui" then return { instance = { view = view } } end
            return require(name)
        end,
    }, { __index = _G })
    setfenv(chunk, env)
    menu_items.page_turns = chunk()
end

local function fromModule(path, id, menu_items, extra)
    local Module = require(path)
    local ui, view = standIn()
    local fake = setmetatable(extra or {}, { __index = Module })
    fake.ui, fake.view, fake.document = ui, view, ui.document
    fake.screen_w = Device.screen:getWidth()
    local out = {}
    Module.addToMainMenu(fake, out)
    menu_items[id] = out[id]
end

function M.add(menu_items)
    M.placeInOrder()
    local builders = {
        status_bar = function() statusBar(menu_items) end,
        page_turns = function() if Device:isTouchDevice() then pageTurns(menu_items) end end,
        follow_links = function() fromModule("apps/reader/modules/readerlink", "follow_links", menu_items) end,
        long_press = function() fromModule("apps/reader/modules/readerhighlight", "long_press", menu_items) end,
        translation_settings = function()
            menu_items.translation_settings = require("ui/translator"):genSettingsMenu()
        end,
        fulltext_search_settings = function()
            fromModule("apps/reader/modules/readersearch", "fulltext_search_settings", menu_items, {
                findall_nb_context_words = G_reader_settings:readSetting("fulltext_search_nb_context_words") or 5,
                findall_results_per_page = G_reader_settings:readSetting("fulltext_search_results_per_page") or 10,
                findall_results_max_lines = G_reader_settings:readSetting("fulltext_search_results_max_lines"),
            })
        end,
    }
    for id, build in pairs(builders) do
        local ok, err = pcall(build)
        if not ok then
            logger.warn("[Daf] reader setting", id, err)
            menu_items[id] = nil
        elseif menu_items[id] then
            guard(menu_items[id])
        end
    end
end

return M
