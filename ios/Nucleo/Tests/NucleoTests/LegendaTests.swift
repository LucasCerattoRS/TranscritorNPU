import XCTest
@testable import Nucleo

final class LegendaTests: XCTestCase {
    func testCarimboArredondaAntesDeQuebrar() {
        XCTAssertEqual(Legenda.carimbo(59.9996), "00:01:00,000")
        XCTAssertEqual(Legenda.carimbo(0), "00:00:00,000")
        XCTAssertEqual(Legenda.carimbo(3661.5), "01:01:01,500")
    }

    func testSrtPulaTrechosVaziosENumeraContinuo() {
        let srt = Legenda.srt([
            Trecho(inicio: 0, fim: 1.5, texto: "<|pt|><|0.00|> Olá"),
            Trecho(inicio: 1.5, fim: 3, texto: "   "),
            Trecho(inicio: 3, fim: 4.25, texto: "mundo<|4.25|>"),
        ])
        XCTAssertEqual(srt, "1\n00:00:00,000 --> 00:00:01,500\nOlá\n\n2\n00:00:03,000 --> 00:00:04,250\nmundo\n")
    }

    func testTextoCorrido() {
        XCTAssertEqual(Legenda.texto([Trecho(inicio: 0, fim: 1, texto: " a "), Trecho(inicio: 1, fim: 2, texto: "<|endoftext|>")]), "a")
    }

    func testNomeSeguro() {
        XCTAssertEqual(Legenda.nomeSeguro("a/b:c?*d\u{1}"), "a_b_c__d_")
        XCTAssertEqual(Legenda.nomeSeguro(" .. "), "transcricao")
        XCTAssertEqual(Legenda.nomeSeguro("ação"), "ação")
        let longo = Legenda.nomeSeguro(String(repeating: "é", count: 200))
        XCTAssertLessThanOrEqual(longo.utf8.count, 180)
        XCTAssertEqual(longo, String(repeating: "é", count: 90))
    }
}
