import PhotosUI
import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var fluxo: Fluxo
    @State private var link = ""
    @State private var mostrandoLogin = false
    @State private var escolhendoArquivo = false
    @State private var itemDaGaleria: PhotosPickerItem?
    @AppStorage("modelo") private var modelo = ModeloWhisper.preciso
    @AppStorage("idioma") private var idioma = "pt"

    private let idiomas = [("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol"), ("auto", "Detectar automaticamente")]
    private var codigoIdioma: String? { idioma == "auto" ? nil : idioma }

    var body: some View {
        NavigationStack {
            Form {
                secaoInstagram
                secaoDoIPhone
                secaoOpcoes
                if fluxo.ocupado { secaoProgresso }
                if let resultado = fluxo.resultado { secaoResultado(resultado) }
            }
            .navigationTitle("Transcritor")
        }
        .sheet(isPresented: $mostrandoLogin) {
            LoginInstagramView { Task { await fluxo.atualizarLogin() } }
        }
        .fileImporter(isPresented: $escolhendoArquivo, allowedContentTypes: [.movie, .audio]) { escolha in
            guard case .success(let url) = escolha, let copia = copiarParaTemporario(url) else { return }
            fluxo.processar(arquivo: copia, modelo: modelo, idioma: codigoIdioma)
        }
        .onChange(of: itemDaGaleria) { _, item in
            guard let item else { return }
            itemDaGaleria = nil
            Task {
                if let video = try? await item.loadTransferable(type: VideoDaGaleria.self) {
                    fluxo.processar(arquivo: video.url, modelo: modelo, idioma: codigoIdioma)
                } else {
                    fluxo.erro = "Não consegui abrir esse vídeo da galeria."
                }
            }
        }
        // transcritor://processar?link=<link>: usado pelo atalho da folha de compartilhamento (ver ios/README.md).
        .onOpenURL { url in
            guard let recebido = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "link" })?.value else { return }
            link = recebido
            let soBaixar = url.host == "baixar"
            fluxo.processar(link: recebido, transcrever: !soBaixar, modelo: modelo, idioma: codigoIdioma)
        }
        .alert("Não deu certo", isPresented: Binding(get: { fluxo.erro != nil }, set: { if !$0 { fluxo.erro = nil } })) {
            if !fluxo.logado && fluxo.erro?.contains("login") == true {
                Button("Entrar no Instagram") { mostrandoLogin = true }
            }
            Button("OK", role: .cancel) {}
        } message: {
            Text(fluxo.erro ?? "")
        }
        .task { await fluxo.atualizarLogin() }
    }

    private var secaoInstagram: some View {
        Section {
            HStack {
                TextField("Link do post ou Reel", text: $link)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                PasteButton(payloadType: String.self) { textos in
                    if let texto = textos.first { link = texto }
                }
                .labelStyle(.iconOnly)
                .buttonBorderShape(.capsule)
            }
            Button {
                fluxo.processar(link: link, transcrever: true, modelo: modelo, idioma: codigoIdioma)
            } label: {
                Label("Baixar e transcrever", systemImage: "text.bubble")
            }
            .disabled(link.isEmpty || fluxo.ocupado)
            Button {
                fluxo.processar(link: link, transcrever: false, modelo: modelo, idioma: codigoIdioma)
            } label: {
                Label("Só baixar o vídeo", systemImage: "arrow.down.circle")
            }
            .disabled(link.isEmpty || fluxo.ocupado)
            if fluxo.logado {
                Button("Sair da conta do Instagram", role: .destructive) { Task { await fluxo.sair() } }
            } else {
                Button { mostrandoLogin = true } label: {
                    Label("Entrar no Instagram", systemImage: "person.crop.circle.badge.plus")
                }
            }
        } header: {
            Text("Instagram")
        } footer: {
            Text(fluxo.logado
                 ? "Conectado. No Instagram: Compartilhar › Copiar link, depois cole aqui."
                 : "O Instagram só libera os vídeos com login. A senha é digitada no site do Instagram; o app guarda só a sessão.")
        }
    }

    private var secaoDoIPhone: some View {
        Section("Do iPhone") {
            PhotosPicker(selection: $itemDaGaleria, matching: .videos) {
                Label("Transcrever vídeo da galeria", systemImage: "photo.on.rectangle")
            }
            .disabled(fluxo.ocupado)
            Button { escolhendoArquivo = true } label: {
                Label("Transcrever arquivo (vídeo ou áudio)", systemImage: "folder")
            }
            .disabled(fluxo.ocupado)
        }
    }

    private var secaoOpcoes: some View {
        Section {
            Picker("Modelo", selection: $modelo) {
                ForEach(ModeloWhisper.allCases) { Text($0.nome).tag($0) }
            }
            Picker("Idioma", selection: $idioma) {
                ForEach(idiomas.indices, id: \.self) { i in Text(idiomas[i].1).tag(idiomas[i].0) }
            }
        } header: {
            Text("Transcrição")
        } footer: {
            Text("Roda offline no Neural Engine. O modelo é baixado uma vez; mantenha o app aberto enquanto transcreve.")
        }
        .disabled(fluxo.ocupado)
    }

    private var secaoProgresso: some View {
        Section {
            if let p = fluxo.progresso {
                ProgressView(value: p) { Text(fluxo.status) }
            } else {
                HStack(spacing: 12) {
                    ProgressView()
                    Text(fluxo.status)
                }
            }
        }
    }

    private func secaoResultado(_ resultado: Resultado) -> some View {
        Section("Resultado") {
            if !resultado.texto.isEmpty {
                Text(resultado.texto)
                    .textSelection(.enabled)
                Button {
                    UIPasteboard.general.string = resultado.texto
                } label: {
                    Label("Copiar texto", systemImage: "doc.on.doc")
                }
            }
            ForEach(resultado.arquivos, id: \.self) { arquivo in
                ShareLink(item: arquivo) {
                    Label(arquivo.lastPathComponent, systemImage: icone(de: arquivo))
                }
            }
        }
    }

    private func icone(de arquivo: URL) -> String {
        switch arquivo.pathExtension.lowercased() {
        case "mp4", "mov": return "film"
        case "srt": return "captions.bubble"
        default: return "doc.text"
        }
    }

    /// O arquivo escolhido só fica acessível durante o acesso com escopo de segurança.
    private func copiarParaTemporario(_ url: URL) -> URL? {
        let acessou = url.startAccessingSecurityScopedResource()
        defer { if acessou { url.stopAccessingSecurityScopedResource() } }
        let destino = FileManager.default.temporaryDirectory.appendingPathComponent(url.lastPathComponent)
        try? FileManager.default.removeItem(at: destino)
        do {
            try FileManager.default.copyItem(at: url, to: destino)
            return destino
        } catch {
            fluxo.erro = "Não consegui abrir o arquivo: \(error.localizedDescription)"
            return nil
        }
    }
}

/// Vídeo vindo da galeria, copiado para uma pasta temporária com um nome legível.
struct VideoDaGaleria: Transferable {
    let url: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { video in
            SentTransferredFile(video.url)
        } importing: { recebido in
            let formato = DateFormatter()
            formato.dateFormat = "yyyy-MM-dd_HH-mm-ss"
            let nome = "galeria_\(formato.string(from: Date())).\(recebido.file.pathExtension)"
            let copia = FileManager.default.temporaryDirectory.appendingPathComponent(nome)
            try? FileManager.default.removeItem(at: copia)
            try FileManager.default.copyItem(at: recebido.file, to: copia)
            return Self(url: copia)
        }
    }
}
