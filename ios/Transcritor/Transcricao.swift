import AVFoundation
import Foundation
import Nucleo
import WhisperKit

enum ModeloWhisper: String, CaseIterable, Identifiable {
    case preciso = "openai_whisper-large-v3-v20240930_626MB"
    case rapido = "openai_whisper-small"

    var id: String { rawValue }

    var nome: String {
        switch self {
        case .preciso: return "Preciso (large-v3 turbo, ~630 MB)"
        case .rapido: return "Rápido (small)"
        }
    }
}

enum ErroTranscricao: Error, LocalizedError {
    case semAudio
    case falhaAudio
    case semFala

    var errorDescription: String? {
        switch self {
        case .semAudio: return "Esse vídeo não tem faixa de áudio."
        case .falhaAudio: return "Não consegui extrair o áudio do vídeo."
        case .semFala: return "Nenhuma fala foi reconhecida no áudio."
        }
    }
}

/// Whisper no Neural Engine via WhisperKit. Mantém um modelo carregado por vez, como o
/// `obter_pipeline` do app.py mantém um pipeline por dispositivo.
actor Transcritor {
    static let compartilhado = Transcritor()

    private var carregado: (modelo: ModeloWhisper, kit: WhisperKit)?

    /// Fora de Documentos para os ~600 MB do modelo não aparecerem no app Arquivos.
    private let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Modelos", isDirectory: true)

    func transcrever(video: URL, modelo: ModeloWhisper, idioma: String?,
                     aviso: @escaping @Sendable (String, Double?) -> Void) async throws -> [Trecho] {
        aviso("Extraindo o áudio…", nil)
        let audio = try await Self.extrairAudio(de: video)
        defer { try? FileManager.default.removeItem(at: audio) }

        let kit = try await preparar(modelo, aviso: aviso)
        aviso("Transcrevendo… (deixe o app aberto)", nil)
        let opcoes = DecodingOptions(
            task: .transcribe,
            language: idioma,
            detectLanguage: idioma == nil,
            skipSpecialTokens: true,
            chunkingStrategy: .vad
        )
        let resultados = try await kit.transcribe(audioPath: audio.path, decodeOptions: opcoes)
        let trechos = resultados.flatMap(\.segments).map {
            Trecho(inicio: Double($0.start), fim: Double($0.end), texto: $0.text)
        }
        guard !Legenda.texto(trechos).isEmpty else { throw ErroTranscricao.semFala }
        return trechos
    }

    private func preparar(_ modelo: ModeloWhisper,
                          aviso: @escaping @Sendable (String, Double?) -> Void) async throws -> WhisperKit {
        if let carregado, carregado.modelo == modelo { return carregado.kit }
        carregado = nil

        // Guarda o caminho relativo: a pasta do app muda de lugar a cada reinstalação.
        let chave = "pastaModelo.\(modelo.rawValue)"
        var pasta = UserDefaults.standard.string(forKey: chave).map { base.appendingPathComponent($0) }
        if pasta.map({ !FileManager.default.fileExists(atPath: $0.path) }) ?? true {
            aviso("Baixando o modelo (só na primeira vez)…", 0)
            let baixada = try await WhisperKit.download(variant: modelo.rawValue, downloadBase: base) { p in
                aviso("Baixando o modelo (só na primeira vez)…", p.fractionCompleted)
            }
            let relativo = baixada.standardizedFileURL.path
                .replacingOccurrences(of: base.standardizedFileURL.path + "/", with: "")
            UserDefaults.standard.set(relativo, forKey: chave)
            pasta = baixada
        }

        aviso("Preparando o modelo no Neural Engine… (na primeira vez pode levar alguns minutos)", nil)
        let config = WhisperKitConfig(
            modelFolder: pasta!.path,
            verbose: false,
            logLevel: .error,
            prewarm: true,
            load: true,
            download: false
        )
        let kit = try await WhisperKit(config)
        carregado = (modelo, kit)
        return kit
    }

    /// Só a faixa de áudio, em .m4a: o WhisperKit lê m4a direto.
    static func extrairAudio(de video: URL) async throws -> URL {
        let asset = AVURLAsset(url: video)
        guard try await !asset.loadTracks(withMediaType: .audio).isEmpty else { throw ErroTranscricao.semAudio }
        guard let exportacao = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A) else {
            throw ErroTranscricao.falhaAudio
        }
        let saida = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".m4a")
        if #available(iOS 18, *) {
            try await exportacao.export(to: saida, as: .m4a)
        } else {
            exportacao.outputURL = saida
            exportacao.outputFileType = .m4a
            await exportacao.export()
            guard exportacao.status == .completed else { throw exportacao.error ?? ErroTranscricao.falhaAudio }
        }
        return saida
    }
}
