import Foundation

/// Um trecho transcrito com início e fim em segundos.
public struct Trecho: Equatable, Sendable {
    public var inicio: Double
    public var fim: Double
    public var texto: String

    public init(inicio: Double, fim: Double, texto: String) {
        self.inicio = inicio
        self.fim = fim
        self.texto = texto
    }
}

/// Mesmas regras do `app.py` (`_ts_srt`, `gerar_srt`, `_nome_seguro`), portadas para Swift.
public enum Legenda {
    /// Arredonda para milissegundos ANTES de quebrar em h/m/s; senão 59.9996 vira "00:00:60,000".
    public static func carimbo(_ segundos: Double) -> String {
        // .toNearestOrEven imita o round() do Python.
        var ms = max(0, Int((segundos * 1000).rounded(.toNearestOrEven)))
        let h = ms / 3_600_000
        ms %= 3_600_000
        let m = ms / 60_000
        ms %= 60_000
        let s = ms / 1000
        ms %= 1000
        return String(format: "%02d:%02d:%02d,%03d", h, m, s, ms)
    }

    /// Tira os marcadores especiais do Whisper (`<|pt|>`, `<|0.00|>`…) e os espaços das pontas.
    public static func limpar(_ texto: String) -> String {
        texto.replacingOccurrences(of: #"<\|[^|]*\|>"#, with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Trechos sem texto (silêncio) ficam de fora e a numeração segue contínua.
    public static func srt(_ trechos: [Trecho]) -> String {
        trechos
            .map { Trecho(inicio: $0.inicio, fim: $0.fim, texto: limpar($0.texto)) }
            .filter { !$0.texto.isEmpty }
            .enumerated()
            .map { i, t in "\(i + 1)\n\(carimbo(t.inicio)) --> \(carimbo(t.fim))\n\(t.texto)\n" }
            .joined(separator: "\n")
    }

    /// Texto corrido para o .txt: um trecho por linha, sem os vazios.
    public static func texto(_ trechos: [Trecho]) -> String {
        trechos.map { limpar($0.texto) }.filter { !$0.isEmpty }.joined(separator: "\n")
    }

    /// Título vira nome de arquivo: troca < > : " / \ | ? * e caracteres de controle por "_".
    public static func nomeSeguro(_ nome: String) -> String {
        let proibidos = Set("<>:\"/\\|?*")
        var limpo = String(nome.map { c -> Character in
            if proibidos.contains(c) || c.unicodeScalars.contains(where: { $0.value < 0x20 }) { return "_" }
            return c
        })
        // Reserva espaço para carimbo e extensão no limite de 255 bytes, sem cortar um caractere ao meio.
        while limpo.utf8.count > 180 { limpo.removeLast() }
        limpo = limpo.trimmingCharacters(in: CharacterSet(charactersIn: " ."))
        return limpo.isEmpty ? "transcricao" : limpo
    }
}
