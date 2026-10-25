import AppKit
import SwiftUI

/// Focus mode, as the page has it (web/focus.js): what's being read on the whole screen, and nothing
/// else. The window goes full screen with the menu bar and the toolbar hidden until the pointer goes
/// to the top of the screen, which is the Mac's way of bringing a bar back; in the main window the
/// sidebar and the list go, and the readers' side panels close. View › Focus Mode (⇧⌘F), the [ ]
/// button in a reader's toolbar, F in a book and ⇧F in an article; the same again, Esc, or leaving
/// full screen leaves it.
@MainActor
@Observable
final class Focus {
    static let shared = Focus()
    /// The windows in focus mode, by number.
    private(set) var on: Set<Int> = []
    /// Goes up whenever a window starts focus mode, for its readers to put their panels away.
    private(set) var started = 0
    /// Windows whose toolbar Daf hides itself (when the Mac keeps it in full screen), shown again
    /// while the pointer is at the top of the screen.
    @ObservationIgnored private var tucked: Set<Int> = []
    @ObservationIgnored private var mouse: Any?
    /// The main window's panes as they were (collapsed or not) before focus mode put them away.
    @ObservationIgnored private var panes: [Int: [Bool]] = [:]

    private static let options: NSApplication.PresentationOptions = [.fullScreen, .autoHideMenuBar, .autoHideToolbar, .autoHideDock]

    private init() {
        let center = NotificationCenter.default
        center.addObserver(forName: NSWindow.didEnterFullScreenNotification, object: nil, queue: .main) { n in
            let w = n.object as? NSWindow
            MainActor.assumeIsolated { if let w, Focus.shared.isOn(w) { Focus.shared.tuck(w) } }
        }
        center.addObserver(forName: NSWindow.didExitFullScreenNotification, object: nil, queue: .main) { n in
            let w = n.object as? NSWindow
            MainActor.assumeIsolated { if let w { Focus.shared.on.remove(w.windowNumber); Focus.shared.untuck(w); Focus.shared.uncollapse(w) } }
        }
        // Esc leaves it, when nothing else in the window wants Esc (a sheet, a field being typed in)
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { e in
            guard e.keyCode == 53, e.modifierFlags.intersection([.command, .control, .option, .shift]).isEmpty else { return e }
            return MainActor.assumeIsolated {
                guard let w = NSApp.keyWindow, Focus.shared.isOn(w), w.attachedSheet == nil else { return e }
                if let tv = w.firstResponder as? NSTextView, tv.isEditable { return e }
                Focus.shared.leave(w)
                return nil
            }
        }
    }

    func isOn(_ w: NSWindow?) -> Bool { w.map { on.contains($0.windowNumber) } ?? false }
    /// The main window (the lists and what's open in it) is in focus mode.
    var main: Bool { NSApp.windows.contains { Self.isMain($0) && on.contains($0.windowNumber) } }
    static func isMain(_ w: NSWindow) -> Bool { w.identifier?.rawValue.hasPrefix("main") == true }

    func toggle(_ w: NSWindow? = NSApp.keyWindow) {
        guard let w else { return }
        if isOn(w) { leave(w) } else { enter(w) }
    }

    func enter(_ w: NSWindow) {
        on.insert(w.windowNumber)
        started += 1
        if Self.isMain(w) { AppModel.shared.showInspector = false; collapse(w) }
        if w.styleMask.contains(.fullScreen) { tuck(w) } else { w.toggleFullScreen(nil) }
    }

    func leave(_ w: NSWindow) {
        on.remove(w.windowNumber)
        untuck(w)
        uncollapse(w)
        if w.styleMask.contains(.fullScreen) { w.toggleFullScreen(nil) }
    }

    /// The split view that holds the main window's sidebar, list and what's open.
    private static func split(_ w: NSWindow) -> NSSplitViewController? {
        func find(_ v: NSView) -> NSSplitView? { (v as? NSSplitView) ?? v.subviews.lazy.compactMap(find).first }
        return w.contentView.flatMap(find)?.delegate as? NSSplitViewController
    }

    /// Every pane but the last (what's open) put away, as they were kept for after.
    private func collapse(_ w: NSWindow) {
        guard let s = Self.split(w), s.splitViewItems.count > 1 else { return }
        panes[w.windowNumber] = s.splitViewItems.map(\.isCollapsed)
        for item in s.splitViewItems.dropLast() where !item.isCollapsed { item.animator().isCollapsed = true }
    }

    private func uncollapse(_ w: NSWindow) {
        guard let was = panes.removeValue(forKey: w.windowNumber), let s = Self.split(w) else { return }
        for (item, c) in zip(s.splitViewItems, was) where item.isCollapsed != c { item.animator().isCollapsed = c }
    }

    /// The toolbar hidden till the pointer goes to the top: the Mac's own way (with the menu bar)
    /// when it will, else Daf's.
    private func tuck(_ w: NSWindow) {
        NSApp.presentationOptions = Self.options
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            MainActor.assumeIsolated {
                guard Focus.shared.isOn(w), w.styleMask.contains(.fullScreen) else { return }
                if !NSApp.presentationOptions.contains(.autoHideToolbar) { NSApp.presentationOptions = Self.options }
                if !NSApp.presentationOptions.contains(.autoHideToolbar) { Focus.shared.hideBar(w) }
            }
        }
    }

    private func hideBar(_ w: NSWindow) {
        tucked.insert(w.windowNumber)
        w.toolbar?.isVisible = false
        w.acceptsMouseMovedEvents = true
        guard mouse == nil else { return }
        mouse = NSEvent.addLocalMonitorForEvents(matching: [.mouseMoved, .leftMouseDragged]) { e in
            let w = e.window
            MainActor.assumeIsolated {
                guard let w, Focus.shared.tucked.contains(w.windowNumber), let top = w.screen?.frame.maxY else { return }
                let from = top - NSEvent.mouseLocation.y
                if from < 8, w.toolbar?.isVisible == false { w.toolbar?.isVisible = true }
                else if from > 150, w.toolbar?.isVisible == true { w.toolbar?.isVisible = false }
            }
            return e
        }
    }

    private func untuck(_ w: NSWindow) {
        guard tucked.remove(w.windowNumber) != nil else { return }
        w.toolbar?.isVisible = true
    }

    /// The toolbar is out of the way: hidden by the Mac until the top, or by Daf.
    func barTucked(_ w: NSWindow) -> Bool { NSApp.presentationOptions.contains(.autoHideToolbar) || tucked.contains(w.windowNumber) }
}

/// The [ ] button in a reader's toolbar: focus mode for its window.
struct FocusButton: View {
    @State private var window: NSWindow?

    var body: some View {
        let on = Focus.shared.isOn(window)
        Button { Focus.shared.toggle(window ?? NSApp.keyWindow) } label: {
            Label(on ? "Leave Focus Mode" : "Focus Mode", systemImage: on ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
        }
        .help(on ? "Leave focus mode (Esc)" : "Focus mode: only what you're reading, on the whole screen (⇧⌘F)")
        .background(WindowFinder { window = $0 })
    }
}
