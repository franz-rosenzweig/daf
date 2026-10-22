import Charts
import SwiftUI

/// Stats, as the page has them (/api/stats), drawn with Apple's charts.
struct StatsView: View {
    @Environment(AppModel.self) private var model
    @State private var s: J?

    var body: some View {
        ScrollView {
            if let s {
                VStack(alignment: .leading, spacing: 28) {
                    numbers(s)
                    let goal = s.d("goal") ?? 60
                    Panel("The last two weeks") {
                        Chart(Array(s.a("days14").enumerated()), id: \.offset) { _, d in
                            BarMark(x: .value("Day", Self.day(d.s("date"))), y: .value("Minutes", d.d("minutes") ?? 0))
                                .foregroundStyle((d.d("minutes") ?? 0) >= goal ? Color.daf : Color.daf.opacity(0.45))
                            RuleMark(y: .value("Goal", goal)).lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3])).foregroundStyle(.secondary)
                        }
                        .frame(height: 180)
                    }
                    HStack(alignment: .top, spacing: 20) {
                        Panel("Where the minutes come from") {
                            Chart(s.a("sources"), id: \.self) { x in
                                SectorMark(angle: .value("Minutes", x.d("minutes") ?? 0), innerRadius: .ratio(0.6), angularInset: 1.5)
                                    .foregroundStyle(by: .value("Source", x.s("label") ?? ""))
                            }
                            .chartLegend(position: .trailing, alignment: .center)
                            .frame(height: 180)
                        }
                        Panel("Highlights a week") {
                            Chart(s.a("highlight_weeks"), id: \.self) { w in
                                LineMark(x: .value("Week", Self.day(w.s("week"))), y: .value("Highlights", w.d("n") ?? 0))
                                    .interpolationMethod(.catmullRom)
                                AreaMark(x: .value("Week", Self.day(w.s("week"))), y: .value("Highlights", w.d("n") ?? 0))
                                    .interpolationMethod(.catmullRom).foregroundStyle(Color.daf.opacity(0.15))
                            }
                            .frame(height: 180)
                        }
                    }
                    HStack(alignment: .top, spacing: 20) {
                        Panel("By the hour") {
                            Chart(Array(s.list("hours").enumerated()), id: \.offset) { h, v in
                                BarMark(x: .value("Hour", h), y: .value("Minutes", (v as? NSNumber)?.doubleValue ?? 0))
                            }
                            .chartXScale(domain: 0...23)
                            .frame(height: 140)
                        }
                        Panel("By the day of the week") {
                            Chart(Array(s.list("weekdays").enumerated()), id: \.offset) { k, v in
                                BarMark(x: .value("Day", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][k % 7]), y: .value("Minutes", (v as? NSNumber)?.doubleValue ?? 0))
                            }
                            .frame(height: 140)
                        }
                    }
                    books("Reading now", s.a("in_progress"))
                    books("Waiting for you", s.a("stalled"))
                    books("Finished", s.a("finished"))
                }
                .padding(28)
                .frame(maxWidth: 1000)
                .frame(maxWidth: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(60)
            }
        }
        .navigationTitle("Stats")
        .task { s = try? await API.shared.json("/api/stats") }
    }

    private func numbers(_ s: J) -> some View {
        let t = s.o("totals"), st = s.o("streak")
        return Grid(horizontalSpacing: 14, verticalSpacing: 14) {
            GridRow {
                Number(value: "\(Int(t?.d("today") ?? 0))′", label: "Today")
                Number(value: "\(Int(t?.d("week") ?? 0))′", label: "This week")
                Number(value: "\(Int(t?.d("month") ?? 0))′", label: "This month")
                Number(value: "\(Int(t?.d("avg30") ?? 0))′", label: "A day, last 30 days")
            }
            GridRow {
                Number(value: String(format: "%.1f h", t?.d("year30_hours") ?? 0), label: "Year 30 so far")
                Number(value: "\(t?.i("year30_days_read") ?? 0) of \(t?.i("year30_elapsed") ?? 0)", label: "Days I read")
                Number(value: "\(st?.i("any") ?? 0)", label: "Days in a row (best \(st?.i("best_any") ?? 0))")
                Number(value: "\(st?.i("goal") ?? 0)", label: "Goal days in a row (best \(st?.i("best_goal") ?? 0))")
            }
        }
    }

    @ViewBuilder
    private func books(_ title: String, _ list: [J]) -> some View {
        if !list.isEmpty {
            Panel(title) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 14) {
                        ForEach(list, id: \.self) { b in
                            VStack(alignment: .leading, spacing: 4) {
                                Thumb(path: b.b("has_cover") ? "/api/cover/" + API.enc(b.s("id") ?? "") : nil, book: true)
                                    .frame(width: 40, height: 60)
                                Text(b.s("title") ?? "").font(.caption.weight(.semibold)).lineLimit(2)
                                Text(b.s("note") ?? "").font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                            }
                            .frame(width: 110, alignment: .leading)
                        }
                    }
                }
            }
        }
    }

    static func day(_ iso: String?) -> String {
        guard let iso, iso.count >= 10 else { return iso ?? "" }
        let m = Int(iso.dropFirst(5).prefix(2)) ?? 0, d = Int(iso.dropFirst(8).prefix(2)) ?? 0
        return "\(d)/\(m)"
    }
}

struct Number: View {
    let value: String
    let label: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value).font(.system(.title2, design: .rounded).weight(.semibold)).monospacedDigit()
            Text(label).font(.caption).foregroundStyle(.secondary).lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Theme.shared.card, in: RoundedRectangle(cornerRadius: 10))
    }
}

struct Panel<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content
    init(_ title: String, @ViewBuilder content: () -> Content) { self.title = title; self.content = content() }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
