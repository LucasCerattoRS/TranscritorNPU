import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public struct VideoInstagram: Equatable, Sendable {
    public let url: URL
    public let largura: Int
    public let altura: Int
}

public struct MidiaInstagram: Equatable, Sendable {
    public let codigo: String
    public let autor: String?
    public let legenda: String?
    /// Um por vídeo do post (carrossel pode ter vários), já na maior resolução.
    public let videos: [VideoInstagram]

    /// Base dos nomes de arquivo: "instagram_<autor>_<código>".
    public var nomeBase: String {
        Legenda.nomeSeguro(["instagram", autor, codigo].compactMap { $0 }.joined(separator: "_"))
    }
}

public enum ErroInstagram: Error, Equatable, LocalizedError {
    case linkInvalido
    case precisaLogin
    case semVideo
    case naoEncontrado
    case limiteDeAcesso
    case respostaInesperada
    case http(Int)

    public var errorDescription: String? {
        switch self {
        case .linkInvalido: return "Link do Instagram não reconhecido. Use o link de um post ou Reel (Compartilhar → Copiar link)."
        case .precisaLogin: return "O Instagram pediu login. Toque em \"Entrar no Instagram\" e tente de novo."
        case .semVideo: return "Esse post não tem vídeo (é só foto)."
        case .naoEncontrado: return "Post privado, removido ou indisponível."
        case .limiteDeAcesso: return "O Instagram limitou os acessos por agora. Espere alguns minutos e tente de novo."
        case .respostaInesperada: return "O Instagram respondeu algo inesperado. Pode ter mudado; tente de novo mais tarde."
        case .http(let status): return "O Instagram recusou o pedido (HTTP \(status))."
        }
    }
}

/// Mesmo caminho que o yt-dlp usa com login: `GET /api/v1/media/<pk>/info/` com os cookies da sessão.
public enum Instagram {
    static let alfabeto = Array("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    public static let appID = "936619743392459"

    static func ehInstagram(_ url: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http",
              let host = url.host?.lowercased() else { return false }
        return host == "instagram.com" || host.hasSuffix(".instagram.com") || host == "instagr.am"
    }

    /// Código do post em links /p/, /reel/, /reels/ e /tv/ (com ou sem o @usuário antes).
    public static func codigo(de link: String) -> String? {
        guard let url = URL(string: link.trimmingCharacters(in: .whitespacesAndNewlines)), ehInstagram(url) else { return nil }
        let partes = url.path.split(separator: "/").map(String.init)
        guard let i = partes.firstIndex(where: { ["p", "reel", "reels", "tv"].contains($0) }),
              i <= 1, i + 1 < partes.count else { return nil }
        // /share/reel/<x> é um link de compartilhamento: o código real só aparece depois do redirecionamento.
        if i == 1 && partes[0] == "share" { return nil }
        let codigo = partes[i + 1]
        guard !codigo.isEmpty, codigo.allSatisfy({ alfabeto.contains($0) }) else { return nil }
        return codigo
    }

    /// Links instagram.com/share/... precisam ser abertos para revelar o código do post.
    public static func ehCompartilhamento(_ link: String) -> Bool {
        guard let url = URL(string: link.trimmingCharacters(in: .whitespacesAndNewlines)), ehInstagram(url) else { return false }
        return url.path.split(separator: "/").first == "share"
    }

    /// Código do post (base64 do Instagram) para o id numérico; posts privados têm 28 caracteres extras no fim.
    public static func pk(doCodigo codigo: String) -> UInt64? {
        let base = codigo.count > 28 ? String(codigo.dropLast(28)) : codigo
        guard !base.isEmpty else { return nil }
        var valor: UInt64 = 0
        for c in base {
            guard let d = alfabeto.firstIndex(of: c) else { return nil }
            let (vezes, estourou1) = valor.multipliedReportingOverflow(by: 64)
            let (soma, estourou2) = vezes.addingReportingOverflow(UInt64(d))
            if estourou1 || estourou2 { return nil }
            valor = soma
        }
        return valor
    }

    public static func requisicaoInfo(pk: UInt64, cookies: [HTTPCookie], userAgent: String) -> URLRequest {
        var req = URLRequest(url: URL(string: "https://www.instagram.com/api/v1/media/\(pk)/info/")!)
        req.httpShouldHandleCookies = false
        for (campo, valor) in HTTPCookie.requestHeaderFields(with: cookies) {
            req.setValue(valor, forHTTPHeaderField: campo)
        }
        if let csrf = cookies.first(where: { $0.name == "csrftoken" })?.value {
            req.setValue(csrf, forHTTPHeaderField: "X-CSRFToken")
        }
        req.setValue(appID, forHTTPHeaderField: "X-IG-App-ID")
        req.setValue("359341", forHTTPHeaderField: "X-ASBD-ID")
        req.setValue("0", forHTTPHeaderField: "X-IG-WWW-Claim")
        req.setValue("XMLHttpRequest", forHTTPHeaderField: "X-Requested-With")
        req.setValue("https://www.instagram.com", forHTTPHeaderField: "Origin")
        req.setValue("https://www.instagram.com/", forHTTPHeaderField: "Referer")
        req.setValue("*/*", forHTTPHeaderField: "Accept")
        req.setValue(userAgent, forHTTPHeaderField: "User-Agent")
        return req
    }

    /// Traduz a resposta HTTP num erro amigável; nil quando dá para seguir e ler o JSON.
    public static func erro(status: Int, urlFinal: URL?, corpo: Data) -> ErroInstagram? {
        if let caminho = urlFinal?.path, caminho.hasPrefix("/accounts/login") || caminho.hasPrefix("/challenge") {
            return .precisaLogin
        }
        let texto = String(decoding: corpo.prefix(2000), as: UTF8.self).lowercased()
        if texto.contains("login_required") || texto.contains("checkpoint_required") { return .precisaLogin }
        switch status {
        case 200: return nil
        case 401, 403: return .precisaLogin
        case 404: return .naoEncontrado
        case 429: return .limiteDeAcesso
        case 400 where texto.contains("media not found") || texto.contains("invalid media"): return .naoEncontrado
        default: return .http(status)
        }
    }

    public static func midia(doJSON dados: Data, codigo: String) throws -> MidiaInstagram {
        guard let raiz = (try? JSONSerialization.jsonObject(with: dados)) as? [String: Any] else {
            // Página HTML no lugar do JSON costuma ser a tela de login.
            throw String(decoding: dados.prefix(500), as: UTF8.self).contains("<html") ? ErroInstagram.precisaLogin : .respostaInesperada
        }
        guard let item = (raiz["items"] as? [[String: Any]])?.first else { throw ErroInstagram.naoEncontrado }
        let partes = (item["carousel_media"] as? [[String: Any]]) ?? [item]
        let videos = partes.compactMap(melhorVideo)
        guard !videos.isEmpty else { throw ErroInstagram.semVideo }
        let autor = (item["user"] as? [String: Any])?["username"] as? String
        let legenda = (item["caption"] as? [String: Any])?["text"] as? String
        return MidiaInstagram(codigo: codigo, autor: autor, legenda: legenda, videos: videos)
    }

    static func melhorVideo(_ parte: [String: Any]) -> VideoInstagram? {
        let versoes = (parte["video_versions"] as? [[String: Any]]) ?? []
        return versoes.compactMap { v -> VideoInstagram? in
            guard let s = v["url"] as? String, let url = URL(string: s), url.scheme == "https" else { return nil }
            return VideoInstagram(url: url, largura: v["width"] as? Int ?? 0, altura: v["height"] as? Int ?? 0)
        }.max { $0.largura * $0.altura < $1.largura * $1.altura }
    }
}
