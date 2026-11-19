import Foundation
import WebKit
import Nucleo

/// Acesso ao Instagram com a sessão do próprio usuário, feita na tela de login dentro do app.
enum InstagramCliente {
    /// O mesmo navegador no login e nas chamadas da API, para a sessão não parecer vir de outro aparelho.
    static let userAgent = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1"

    @MainActor
    static func cookies() async -> [HTTPCookie] {
        await WKWebsiteDataStore.default().httpCookieStore.allCookies()
            .filter { $0.domain.hasSuffix("instagram.com") }
    }

    @MainActor
    static func logado() async -> Bool {
        await cookies().contains { $0.name == "sessionid" && !$0.value.isEmpty }
    }

    @MainActor
    static func sair() async {
        let loja = WKWebsiteDataStore.default()
        let tipos = WKWebsiteDataStore.allWebsiteDataTypes()
        let registros = await loja.dataRecords(ofTypes: tipos).filter { $0.displayName.contains("instagram") }
        await loja.removeData(ofTypes: tipos, for: registros)
    }

    static func buscarMidia(link: String) async throws -> MidiaInstagram {
        let jar = await cookies()
        var codigo = Instagram.codigo(de: link)
        if codigo == nil, Instagram.ehCompartilhamento(link),
           let url = URL(string: link.trimmingCharacters(in: .whitespacesAndNewlines)) {
            // instagram.com/share/... redireciona para o link do post, que tem o código.
            let (_, resposta) = try await URLSession.shared.data(for: requisicao(url, cookies: jar))
            codigo = resposta.url.flatMap { Instagram.codigo(de: $0.absoluteString) }
        }
        guard let codigo, let pk = Instagram.pk(doCodigo: codigo) else { throw ErroInstagram.linkInvalido }
        guard jar.contains(where: { $0.name == "sessionid" }) else { throw ErroInstagram.precisaLogin }

        let (dados, resposta) = try await URLSession.shared.data(
            for: Instagram.requisicaoInfo(pk: pk, cookies: jar, userAgent: userAgent))
        let status = (resposta as? HTTPURLResponse)?.statusCode ?? 0
        if let erro = Instagram.erro(status: status, urlFinal: resposta.url, corpo: dados) { throw erro }
        return try Instagram.midia(doJSON: dados, codigo: codigo)
    }

    static func baixar(_ video: VideoInstagram, para destino: URL,
                       progresso: @escaping @Sendable (Double) -> Void) async throws {
        let observador = ObservadorDeProgresso(aoProgredir: progresso)
        let (temporario, resposta) = try await URLSession.shared.download(
            for: requisicao(video.url, cookies: []), delegate: observador)
        let status = (resposta as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 200 else {
            try? FileManager.default.removeItem(at: temporario)
            throw ErroInstagram.http(status)
        }
        try? FileManager.default.removeItem(at: destino)
        try FileManager.default.moveItem(at: temporario, to: destino)
    }

    private static func requisicao(_ url: URL, cookies: [HTTPCookie]) -> URLRequest {
        var req = URLRequest(url: url)
        req.httpShouldHandleCookies = false
        for (campo, valor) in HTTPCookie.requestHeaderFields(with: cookies) {
            req.setValue(valor, forHTTPHeaderField: campo)
        }
        req.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        return req
    }
}

/// O `download(for:delegate:)` não dá progresso direto; observa o `Progress` da tarefa criada.
private final class ObservadorDeProgresso: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private let aoProgredir: @Sendable (Double) -> Void
    private var observacao: NSKeyValueObservation?

    init(aoProgredir: @escaping @Sendable (Double) -> Void) {
        self.aoProgredir = aoProgredir
    }

    func urlSession(_ session: URLSession, didCreateTask task: URLSessionTask) {
        let aviso = aoProgredir
        observacao = task.progress.observe(\.fractionCompleted) { p, _ in aviso(p.fractionCompleted) }
    }
}
