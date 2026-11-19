import SwiftUI

@main
struct TranscritorApp: App {
    @StateObject private var fluxo = Fluxo()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(fluxo)
        }
    }
}
