# Transcritor para iPhone

App nativo (SwiftUI) que **baixa vídeos do Instagram e transcreve no próprio iPhone**,
offline, com o Whisper no Neural Engine ([WhisperKit](https://github.com/argmaxinc/argmax-oss-swift)).
Não usa o PC nem servidor: o Mac que compila o app é o do GitHub Actions.

Também transcreve vídeos da galeria e arquivos de áudio/vídeo do app Arquivos.

## Estado

Primeira versão, **ainda não testada num iPhone de verdade**. A lógica pura (links do
Instagram, legenda SRT, nomes de arquivo) tem testes em `Nucleo/` que rodam no Linux; o
app só é compilado no GitHub Actions. O download do Instagram depende de uma API não
oficial (a mesma que o yt-dlp usa com login) e pode quebrar quando o Instagram mudar.

## Instalar no iPhone (grátis, com Apple ID comum)

A Apple não deixa instalar apps fora da App Store sem assinatura. Sem pagar a conta de
desenvolvedor (US$ 99/ano), o caminho é o **SideStore**, que assina o app com o seu
Apple ID gratuito, direto no iPhone.

1. **Uma vez só, com um computador** (o notebook Windows serve): siga o guia oficial do
   SideStore em <https://docs.sidestore.io>. Em resumo: instale o iTunes e o **iloader**
   (iloader.app) no PC, ligue o iPhone no cabo e instale o SideStore por ele.
2. No iPhone, instale o **LocalDevVPN** pela App Store. O SideStore precisa dele ligado
   (e de Wi-Fi) para instalar e renovar apps.
3. Ative o **Modo de Desenvolvedor**: Ajustes › Privacidade e Segurança › Modo de
   Desenvolvedor (a opção aparece depois do primeiro app instalado pelo SideStore).
4. Baixe o `Transcritor.ipa` no Safari do iPhone, na release
   [ios-dev](https://github.com/LucasCerattoRS/TranscritorNPU/releases/tag/ios-dev),
   que é atualizada a cada mudança no app.
5. No SideStore: aba **My Apps** › **+** › escolha o `Transcritor.ipa` em Downloads.

Limites do Apple ID gratuito:
- O app vale **7 dias**. O SideStore renova sozinho em segundo plano, ou você toca em
  **Refresh All**; precisa do LocalDevVPN ligado e Wi-Fi. Se vencer, o app não abre até
  renovar, mas os arquivos ficam.
- No máximo **3 apps** do SideStore ao mesmo tempo (o próprio SideStore conta como um).
- Se o iPhone for restaurado, ou o SideStore perder o arquivo de pareamento, o passo 1
  precisa ser refeito com o computador.

## Usar

1. Toque em **Entrar no Instagram** e faça login na página do próprio Instagram. O app
   não vê a senha; ele só guarda a sessão (cookies), como um navegador.
2. No Instagram, no Reel: **Compartilhar › Copiar link**.
3. No Transcritor, toque no botão de colar ao lado do campo e em **Baixar e transcrever**
   (ou **Só baixar o vídeo**).
4. Na primeira transcrição, o app baixa o modelo (cerca de 630 MB no modo Preciso) e o
   prepara para o Neural Engine; isso pode levar alguns minutos. As próximas são rápidas.
   **Deixe o app aberto** enquanto transcreve: o iOS pausa o trabalho em segundo plano.

O vídeo (.mp4), o texto (.txt) e a legenda (.srt) aparecem no fim da tela para
compartilhar ou salvar (o .mp4 pode ir para Fotos pela opção "Salvar vídeo"). Também ficam
em Arquivos › No meu iPhone › Transcritor.

### Atalho na folha de compartilhamento (opcional)

Para mandar um Reel do Instagram direto para o app, sem copiar e colar:

1. App **Atalhos** › **+** › nos detalhes do atalho, ligue **Mostrar na Folha de
   Compartilhamento** e aceite **URLs**.
2. Ações: **Codificar URL** (entrada: Entrada do Atalho), depois **URL** com o texto
   `transcritor://processar?link=` seguido da variável *URL Codificada*, depois
   **Abrir URLs**.
3. No Instagram: **Compartilhar › Mais (…)** › o nome do atalho.

Troque `processar` por `baixar` para só baixar o vídeo, sem transcrever.

## Modelo e desempenho

O iPhone 13 Pro (A15, 6 GB de RAM, Neural Engine de 16 núcleos) roda os dois modelos
oferecidos. O WhisperKit lista o `large-v3-v20240930_626MB` como compatível com o A15:

| Opção no app | Modelo | Quando usar |
|---|---|---|
| Preciso (padrão) | `openai_whisper-large-v3-v20240930_626MB` (large-v3 turbo comprimido) | Melhor para português; é o mesmo modelo do app de PC. |
| Rápido | `openai_whisper-small` | Quando o Preciso estiver lento ou faltar espaço. |

## Estrutura

| Caminho | O que é |
|---|---|
| `project.yml` | Projeto do Xcode em texto ([XcodeGen](https://github.com/yonaskolb/XcodeGen)); o `.xcodeproj` é gerado no CI. |
| `Nucleo/` | Pacote Swift só com Foundation: links e resposta do Instagram, SRT e nomes de arquivo. Testado com `swift test`. |
| `Transcritor/ContentView.swift` | Tela única: link, login, galeria/arquivos, opções, progresso e resultado. |
| `Transcritor/Fluxo.swift` | Orquestra baixar → transcrever → salvar e guarda o estado da tela. |
| `Transcritor/InstagramCliente.swift` | Cookies da sessão (WebKit), chamada à API e download do vídeo. |
| `Transcritor/LoginInstagramView.swift` | Página de login do Instagram dentro do app. |
| `Transcritor/Transcricao.swift` | Extração do áudio (AVFoundation) e WhisperKit. |
| `../.github/workflows/ios.yml` | Testa o `Nucleo` no Linux, compila o `.ipa` sem assinatura no macOS e publica na release `ios-dev`. |

## Desenvolver sem Mac

- Testes do núcleo (Linux ou macOS, com Swift 5.9 ou mais novo): `swift test --package-path ios/Nucleo`.
- O app só compila com o Xcode: faça push e veja o job `ipa` no GitHub Actions.

## Pendências

- Testar no iPhone: login, download de Reel e de carrossel, transcrição com os dois modelos.
- Sem botão de cancelar a transcrição.
- YouTube ainda não é suportado no app iOS (só Instagram, galeria e arquivos).
- Uma extensão de compartilhamento nativa ocuparia mais um App ID do limite gratuito; por isso o atalho.
