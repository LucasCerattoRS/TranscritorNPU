// swift-tools-version: 5.9
// Lógica pura do app iOS (sem UIKit/WhisperKit): roda e é testada também no Linux.
import PackageDescription

let package = Package(
    name: "Nucleo",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [.library(name: "Nucleo", targets: ["Nucleo"])],
    targets: [
        .target(name: "Nucleo"),
        .testTarget(name: "NucleoTests", dependencies: ["Nucleo"]),
    ]
)
