import Foundation
import Nucleo
import UIKit

struct Resultado {
    var texto: String
    /// .mp4, .txt e .srt gerados, para compartilhar ou salvar.
    var arquivos: [URL]
}

enum Pastas {
    /// Em Documentos: aparecem no app Arquivos em "No meu iPhone › Transcritor".
    static let documentos = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    static let videos = documentos.appendingPathComponent("Videos", isDirectory: true)
    static let transcricoes = documentos.appendingPathComponent("Transcricoes", isDirectory: true)

    static func criar() throws {
        for pasta in [videos, transcricoes] {
            try FileManager.default.createDirectory(at: pasta, withIntermediateDirectories: true)
        }
    }
}

@MainActor
final class Fluxo: ObservableObject {
    @Published var ocupado = false
    @Published var status = ""
    @Published var progresso: Double?
    @Published var resultado: Resultado?
    @Published var erro: String?
    @Published var logado = false

    func atualizarLogin() async {
        logado = await InstagramCliente.logado()
    }

    func sair() async {
        await InstagramCliente.sair()
        await atualizarLogin()
    }

    /// Baixa o(s) vídeo(s) do post e, se pedido, transcreve cada um.
    func processar(link: String, transcrever deveTranscrever: Bool, modelo: ModeloWhisper, idioma: String?) {
        executar {
            self.avisar("Buscando o post…", nil)
            let midia = try await InstagramCliente.buscarMidia(link: link)
            var videos: [URL] = []
            for (i, video) in midia.videos.enumerated() {
                let sufixo = midia.videos.count > 1 ? "_\(i + 1)" : ""
                let destino = Pastas.videos.appendingPathComponent(midia.nomeBase + sufixo + ".mp4")
                let rotulo = midia.videos.count > 1 ? "Baixando vídeo \(i + 1) de \(midia.videos.count)…" : "Baixando o vídeo…"
                self.avisar(rotulo, 0)
                try await InstagramCliente.baixar(video, para: destino) { p in
                    Task { @MainActor in self.progresso = p }
                }
                videos.append(destino)
            }
            guard deveTranscrever else { return Resultado(texto: "", arquivos: videos) }
            return try await self.transcrever(videos, modelo: modelo, idioma: idioma)
        }
    }

    /// Vídeo ou áudio que já está no iPhone (galeria ou app Arquivos).
    func processar(arquivo: URL, modelo: ModeloWhisper, idioma: String?) {
        executar {
            try await self.transcrever([arquivo], modelo: modelo, idioma: idioma)
        }
    }

    private func transcrever(_ videos: [URL], modelo: ModeloWhisper, idioma: String?) async throws -> Resultado {
        var textos: [String] = []
        var arquivos: [URL] = videos.filter { $0.path.hasPrefix(Pastas.videos.path) }
        for (i, video) in videos.enumerated() {
            let trechos = try await Transcritor.compartilhado.transcrever(video: video, modelo: modelo, idioma: idioma) { texto, p in
                let rotulo = videos.count > 1 ? "Vídeo \(i + 1) de \(videos.count): \(texto)" : texto
                Task { @MainActor in self.avisar(rotulo, p) }
            }
            let base = Legenda.nomeSeguro(video.deletingPathExtension().lastPathComponent)
            let txt = Pastas.transcricoes.appendingPathComponent(base + ".txt")
            let srt = Pastas.transcricoes.appendingPathComponent(base + ".srt")
            let texto = Legenda.texto(trechos)
            try texto.write(to: txt, atomically: true, encoding: .utf8)
            try Legenda.srt(trechos).write(to: srt, atomically: true, encoding: .utf8)
            textos.append(videos.count > 1 ? "— Vídeo \(i + 1) —\n\(texto)" : texto)
            arquivos += [txt, srt]
        }
        return Resultado(texto: textos.joined(separator: "\n\n"), arquivos: arquivos)
    }

    private func executar(_ tarefa: @escaping () async throws -> Resultado) {
        guard !ocupado else { return }
        ocupado = true
        erro = nil
        resultado = nil
        // A transcrição para quando a tela apaga e o app vai para segundo plano.
        UIApplication.shared.isIdleTimerDisabled = true
        Task {
            defer {
                ocupado = false
                progresso = nil
                status = ""
                UIApplication.shared.isIdleTimerDisabled = false
            }
            do {
                try Pastas.criar()
                resultado = try await tarefa()
            } catch {
                self.erro = error.localizedDescription
                if (error as? ErroInstagram) == .precisaLogin { await atualizarLogin() }
            }
        }
    }

    private func avisar(_ texto: String, _ p: Double?) {
        status = texto
        progresso = p
    }
}
