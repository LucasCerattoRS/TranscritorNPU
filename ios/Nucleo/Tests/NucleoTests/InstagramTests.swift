import XCTest
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
@testable import Nucleo

final class InstagramTests: XCTestCase {
    func testCodigoDosFormatosDeLink() {
        XCTAssertEqual(Instagram.codigo(de: "https://www.instagram.com/reel/C9xYz-_1AbC/?igsh=abc"), "C9xYz-_1AbC")
        XCTAssertEqual(Instagram.codigo(de: "https://instagram.com/p/aye83DjauH/?foo=bar#abc"), "aye83DjauH")
        XCTAssertEqual(Instagram.codigo(de: " https://www.instagram.com/reels/DAbc123/ "), "DAbc123")
        XCTAssertEqual(Instagram.codigo(de: "https://www.instagram.com/tv/BkfuX9UB-eK/"), "BkfuX9UB-eK")
        XCTAssertEqual(Instagram.codigo(de: "https://www.instagram.com/fulano/reel/DAbc123/"), "DAbc123")
        XCTAssertEqual(Instagram.codigo(de: "https://m.instagram.com/p/DAbc123"), "DAbc123")
    }

    func testCodigoRejeitaOutrosLinks() {
        XCTAssertNil(Instagram.codigo(de: "https://www.youtube.com/watch?v=abc"))
        XCTAssertNil(Instagram.codigo(de: "https://www.instagram.com/fulano/"))
        XCTAssertNil(Instagram.codigo(de: "https://www.instagram.com/share/reel/BAxyz/"))
        XCTAssertNil(Instagram.codigo(de: "https://notinstagram.com/p/abc/"))
        XCTAssertNil(Instagram.codigo(de: "ftp://instagram.com/p/abc/"))
        XCTAssertNil(Instagram.codigo(de: "https://www.instagram.com/p/a%20b/"))
        XCTAssertNil(Instagram.codigo(de: "texto qualquer"))
    }

    func testCompartilhamento() {
        XCTAssertTrue(Instagram.ehCompartilhamento("https://www.instagram.com/share/reel/BAxyz/"))
        XCTAssertFalse(Instagram.ehCompartilhamento("https://www.instagram.com/reel/BAxyz/"))
    }

    func testPkDoCodigo() {
        XCTAssertEqual(Instagram.pk(doCodigo: "B"), 1)
        XCTAssertEqual(Instagram.pk(doCodigo: "BA"), 64)
        XCTAssertEqual(Instagram.pk(doCodigo: "-_"), 62 * 64 + 63)
        // Post privado: os últimos 28 caracteres são descartados.
        XCTAssertEqual(Instagram.pk(doCodigo: "BA" + String(repeating: "x", count: 28)), 64)
        XCTAssertNil(Instagram.pk(doCodigo: "a!"))
        XCTAssertNil(Instagram.pk(doCodigo: String(repeating: "_", count: 12)))  // estoura 64 bits
        // Código de 11 caracteres típico de 2024+ cabe em 64 bits.
        XCTAssertNotNil(Instagram.pk(doCodigo: "DAbcdefghij"))
    }

    func testRequisicaoLevaCookiesECabecalhos() throws {
        let cookies = [
            HTTPCookie(properties: [.name: "sessionid", .value: "S", .domain: ".instagram.com", .path: "/"])!,
            HTTPCookie(properties: [.name: "csrftoken", .value: "C", .domain: ".instagram.com", .path: "/"])!,
        ]
        let req = Instagram.requisicaoInfo(pk: 42, cookies: cookies, userAgent: "UA")
        XCTAssertEqual(req.url?.absoluteString, "https://www.instagram.com/api/v1/media/42/info/")
        XCTAssertEqual(req.value(forHTTPHeaderField: "X-CSRFToken"), "C")
        XCTAssertEqual(req.value(forHTTPHeaderField: "X-IG-App-ID"), Instagram.appID)
        XCTAssertEqual(req.value(forHTTPHeaderField: "User-Agent"), "UA")
        let cookie = try XCTUnwrap(req.value(forHTTPHeaderField: "Cookie"))
        XCTAssertTrue(cookie.contains("sessionid=S"))
        XCTAssertFalse(req.httpShouldHandleCookies)
    }

    func testErroPorResposta() {
        let vazio = Data()
        XCTAssertNil(Instagram.erro(status: 200, urlFinal: nil, corpo: vazio))
        XCTAssertEqual(Instagram.erro(status: 200, urlFinal: URL(string: "https://www.instagram.com/accounts/login/?next=x"), corpo: vazio), .precisaLogin)
        XCTAssertEqual(Instagram.erro(status: 400, urlFinal: nil, corpo: Data(#"{"message":"checkpoint_required"}"#.utf8)), .precisaLogin)
        XCTAssertEqual(Instagram.erro(status: 404, urlFinal: nil, corpo: vazio), .naoEncontrado)
        XCTAssertEqual(Instagram.erro(status: 429, urlFinal: nil, corpo: vazio), .limiteDeAcesso)
        XCTAssertEqual(Instagram.erro(status: 500, urlFinal: nil, corpo: vazio), .http(500))
    }

    func testMidiaReelEscolheMaiorResolucao() throws {
        let json = #"""
        {"items":[{"user":{"username":"fulano"},"caption":{"text":"legenda"},
          "video_versions":[
            {"url":"https://cdn.example/baixo.mp4","width":480,"height":854},
            {"url":"https://cdn.example/alto.mp4","width":720,"height":1280},
            {"url":"http://cdn.example/inseguro.mp4","width":1080,"height":1920}]}]}
        """#
        let m = try Instagram.midia(doJSON: Data(json.utf8), codigo: "ABC")
        XCTAssertEqual(m.videos.map(\.url.absoluteString), ["https://cdn.example/alto.mp4"])
        XCTAssertEqual(m.autor, "fulano")
        XCTAssertEqual(m.legenda, "legenda")
        XCTAssertEqual(m.nomeBase, "instagram_fulano_ABC")
    }

    func testMidiaCarrosselPulaFotos() throws {
        let json = #"""
        {"items":[{"caption":null,"carousel_media":[
          {"image_versions2":{}},
          {"video_versions":[{"url":"https://cdn.example/1.mp4","width":1,"height":1}]},
          {"video_versions":[{"url":"https://cdn.example/2.mp4","width":1,"height":1}]}]}]}
        """#
        let m = try Instagram.midia(doJSON: Data(json.utf8), codigo: "X")
        XCTAssertEqual(m.videos.count, 2)
        XCTAssertNil(m.legenda)
        XCTAssertEqual(m.nomeBase, "instagram_X")
    }

    func testMidiaErros() {
        XCTAssertThrowsError(try Instagram.midia(doJSON: Data(#"{"items":[{"image_versions2":{}}]}"#.utf8), codigo: "X")) {
            XCTAssertEqual($0 as? ErroInstagram, .semVideo)
        }
        XCTAssertThrowsError(try Instagram.midia(doJSON: Data(#"{"items":[]}"#.utf8), codigo: "X")) {
            XCTAssertEqual($0 as? ErroInstagram, .naoEncontrado)
        }
        XCTAssertThrowsError(try Instagram.midia(doJSON: Data("<!DOCTYPE html><html>login</html>".utf8), codigo: "X")) {
            XCTAssertEqual($0 as? ErroInstagram, .precisaLogin)
        }
        XCTAssertThrowsError(try Instagram.midia(doJSON: Data("lixo".utf8), codigo: "X")) {
            XCTAssertEqual($0 as? ErroInstagram, .respostaInesperada)
        }
    }
}
