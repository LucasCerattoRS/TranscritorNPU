import SwiftUI
import WebKit

/// Login no próprio site do Instagram: o app nunca vê a senha, só guarda os cookies da sessão.
struct LoginInstagramView: View {
    var aoEntrar: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            WebInstagram {
                aoEntrar()
                dismiss()
            }
            .ignoresSafeArea(edges: .bottom)
            .navigationTitle("Entrar no Instagram")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fechar") { dismiss() }
                }
            }
        }
    }
}

private struct WebInstagram: UIViewRepresentable {
    var aoEntrar: () -> Void

    func makeCoordinator() -> Coordenador { Coordenador(aoEntrar: aoEntrar) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.websiteDataStore.httpCookieStore.add(context.coordinator)
        let web = WKWebView(frame: .zero, configuration: config)
        web.customUserAgent = InstagramCliente.userAgent
        web.navigationDelegate = context.coordinator
        web.load(URLRequest(url: URL(string: "https://www.instagram.com/accounts/login/")!))
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {}

    static func dismantleUIView(_ web: WKWebView, coordinator: Coordenador) {
        web.configuration.websiteDataStore.httpCookieStore.remove(coordinator)
    }

    final class Coordenador: NSObject, WKNavigationDelegate, WKHTTPCookieStoreObserver {
        private let aoEntrar: () -> Void
        private var avisado = false

        init(aoEntrar: @escaping () -> Void) {
            self.aoEntrar = aoEntrar
        }

        // O Instagram é uma página de app único: depois do login nem sempre há navegação nova,
        // então também observa a chegada do cookie de sessão.
        func cookiesDidChange(in cookieStore: WKHTTPCookieStore) { conferir() }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { conferir() }

        private func conferir() {
            Task { @MainActor in
                guard !avisado, await InstagramCliente.logado() else { return }
                avisado = true
                aoEntrar()
            }
        }
    }
}
