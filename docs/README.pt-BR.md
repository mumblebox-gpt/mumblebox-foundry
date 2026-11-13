# Mumblebox 3D Asset Foundry

**Versão do Foundry 0.1.0-preview.27**

[English](../README.md) · [简体中文](README.zh-CN.md) · [Español (Latinoamérica)](README.es-419.md) · [Français](README.fr.md) · [Português (Brasil)](README.pt-BR.md)

**Crie imagens e assets 3D no seu PC, por conta própria ou junto com seu agente de programação.**

O Foundry reúne fluxos de IA em assistentes passo a passo, com configurações iniciais, prévias e resultados salvos que você pode retomar. Dá para começar sem conhecer o ComfyUI. O instalador do Pinokio prepara o aplicativo e as dependências. Os grafos ficam disponíveis quando você quiser ajustar o processo em detalhe.

Experimente criar acessórios de jogo, partes de personagens, cabelos, splats e peças para projetos criativos ou impressão 3D. Confira cada resultado de acordo com o uso que você tem em mente. A geometria gerada pode precisar de edição, retopologia, ajuste ou preparação para impressão.

[Instalar com o Pinokio](PINOKIO.md) · [Versões para baixar](https://github.com/mumblebox-gpt/mumblebox-foundry/releases) · [Conectar um agente](AGENT-SETUP.md) · [Histórico de versões](../CHANGELOG.md)

## Dê um ponto de partida para seu agente de programação

Peça ao agente para gerar um primeiro modelo no Foundry. Depois, continuem o trabalho juntos no Blender ou em outro editor 3D.

- **O MCP dá acesso às ferramentas do Foundry.** O agente pode consultar os fluxos e seus controles, iniciar tarefas, acompanhar o progresso, abrir prévias e recuperar arquivos exportados. Ele usa os mesmos serviços da interface.
- **A skill do Foundry ensina o agente a usar o aplicativo.** Ela ajuda a escolher o fluxo, respeitar as referências e os limites de memória, conferir o resultado e levá-lo para outra ferramenta.
- **A geração roda no seu PC.** Enquanto o Foundry processa o modelo, o agente pode continuar outras tarefas. Você pode conferir as prévias e retomar o resultado salvo pelo assistente.

A ideia é poupar tempo e tokens, deixando para você e o agente as decisões de acabamento. A economia depende da peça, do fluxo e dos ajustes necessários. A skill cresce conforme surgem novos fluxos e sugestões da comunidade. [Guia do MCP e da skill](AGENT-SETUP.md)

## Escolha um fluxo de trabalho

| Fluxo de trabalho | O que ele faz | Quando usar |
| --- | --- | --- |
| **Imagem única ou texto** | O Pixal3D cria a malha a partir de uma imagem. O Hi3D refina a geometria, o Foundry faz a limpeza e o TRELLIS.2 aplica as texturas. Você também pode criar a imagem com uma descrição no assistente. | Para chegar direto à malha com menos etapas e modelos. Experimente uma imagem nítida em três quartos. |
| **Vistas múltiplas** | Gere e confira quatro vistas com os modelos compatíveis do Qwen ou FLUX. O Pixal3D reconstrói a malha. O Hi3D e o TRELLIS.2 cuidam do acabamento. | Humanoides são um bom ponto de partida. As receitas para veículos, acessórios e criaturas ainda estão sendo aprimoradas. |
| **Guiado em 3D** | Combina uma malha inicial do Pixal3D, vistas com câmeras calibradas no Blender, estimativas do MoGe 2 e orientação do Qwen antes da reconstrução. | Para objetos cujos ângulos você quer escolher e conferir. Reserve mais tempo de processamento. |
| **Splat e sólido** | Crie um splat gaussiano com o Idol da Sperid Labs e uma malha de apoio já limpa. Você pode refinar essa malha com o Hi3D. | Para combinar aparência detalhada com geometria mais leve. Inclui vídeo de órbita e comparação das malhas. |
| **Da órbita à malha** | Gere um vídeo de órbita com H3, escolha as vistas alinhadas e reconstrua com Pixal3D. O Hi3D e o TRELLIS.2 fazem o acabamento. | Para conferir os ângulos e tirar vistas borradas ou deformadas antes de reconstruir. |
| **Mesa giratória virtual** | Gere um vídeo de órbita com H3 e reconstrua o objeto por fotogrametria com Meshroom ou COLMAP + OpenMVS. | Para experimentar fotogrametria com as imagens de uma órbita gerada. |
| **CCORE Texto** | Descreva um acessório estilizado. O assistente inclui 12 exemplos editáveis, melhoria opcional da descrição com Qwen, prévia 3D e exportação GLB. | Para criar ferramentas, móveis ou outros acessórios individuais de jogo. |
| **CCORE Imagem + texto** | Use uma imagem e uma descrição. O CCORE interpreta a referência com o projetor visual. Você também pode criar a imagem pelo assistente. | Para aproveitar ou modificar elementos de uma foto, um esboço ou uma imagem renderizada. |
| **HairDeck** | Gere cartões de cabelo, variações e pranchas de prévia. Ajuste o encaixe e os materiais, confira o movimento com cadeias dinâmicas opcionais e exporte em GLB ou VRM. | Para penteados que estejam bem visíveis na referência. O fluxo usa HairDeck e a integração ComfyUI de FengLairh. |
| **Garment Particles · experimental** | Crie e edite roupas com as ferramentas dos autores. Obtenha moldes de costura, prepare a malha e experimente o caimento no Blender. | Para explorar designs de roupa. Confira o encaixe e a deformação no personagem e conte com alguns ajustes. |
| **Criar imagens** | Crie uma imagem ou um par de frente e costas, retoque o resultado, use LoRAs compatíveis e encontre o que salvou na galeria. | Para preparar uma referência ou guardar a própria imagem. |

Cada fluxo tem seu próprio assistente e uma seção no grafo. Os cartões **Em breve** mostram ideias que ainda estão em desenvolvimento.

## Comece seu primeiro projeto

1. Instale o [Pinokio](https://pinokio.co/) e siga o [guia de instalação do Foundry](PINOKIO.md) para adicionar o repositório.
2. Escolha **Install**, depois **Start Foundry** e **Open Foundry**.
3. Abra **Imagem única ou texto**. Importe ou arraste uma imagem, tire uma foto com a webcam, escolha uma imagem da galeria ou crie uma com uma descrição.
4. Confira as prévias e escolha os arquivos de saída. O **Rocket Mode** pode executar as etapas selecionadas e pular as pausas opcionais de revisão.

Se você já usa ComfyUI, siga a [instalação manual](../INSTALL.md) e abra `Mumblebox 3D Asset Foundry.json`. O instalador prepara o software. Quando um fluxo precisar de pesos que ainda não estão disponíveis, o Foundry os baixa no primeiro uso. Reserve espaço para os modelos, os arquivos de trabalho e as exportações.

## Confira e exporte o resultado

Dependendo do fluxo, você pode exportar GLB, FBX, OBJ, BLEND, STL ou SPZ e salvar texturas, prévias ou um pacote ZIP. As malhas detalhadas e reduzidas podem incluir UVs e mapas de textura com bake.

**A retopologia em quadriláteros é opcional.** Imagem única e Vistas múltiplas oferecem QuadriFlow e Instant Meshes na CPU, além de CyberRemesher em GPU NVIDIA com CUDA. O assistente explica os controles avançados. O QuadriFlow pode usar bastante CPU e demorar. Você também pode manter os triângulos e exportar uma malha texturizada. As prévias em GLB usam triângulos. Os formatos de edição compatíveis preservam as faces de quatro lados.

Confira a deformação, a geometria de impressão ou colisão e os materiais na ferramenta em que você vai usar o modelo. HairDeck pode gerar um GLB estático ou um VRM com ossos dinâmicos. O vídeo mostra o movimento do cabelo. No Garment Particles, o ajuste ao personagem e o caimento ainda são experimentais.

Os pacotes reúnem os arquivos escolhidos, um README, as medições, as somas de verificação, a origem dos recursos e os avisos aplicáveis. Referências particulares, descrições e arquivos de trabalho ficam fora do pacote padrão. Encontre os exports no histórico. Em **Histórico → Vídeos**, você pode reproduzir, baixar ou excluir vídeos que foram salvos separadamente.

## Idioma e acessibilidade

Escolha o idioma no cabeçalho ou em Configurações. A interface muda na hora e mantém seu texto, suas referências, suas prévias e as tarefas em andamento.

O idioma aceito em uma descrição depende do modelo de geração. O Foundry conserva o texto como você digitou.

O autor do CCORE recomenda usar descrições em inglês. Os 12 exemplos acompanham o idioma da interface. O botão **Traduzir para inglês** usa o modelo Qwen local. Confira o resultado antes de gerar. Q4 é o ponto de partida recomendado e ocupa menos VRAM. Q8 usa pesos com mais precisão numérica. A qualidade da tradução pode variar. A tradução exige que o modelo caiba na memória da GPU e preserva sua descrição se o carregamento falhar. Use **Melhorar descrição** para acrescentar detalhes criativos.

Mude o visual com **Tema**. O menu **Fonte** oferece o padrão, 112%, 125%, 150%, 175% e 200%. Abra as opções avançadas quando quiser ajustar mais detalhes.

## Mantenha o Foundry e a skill em dia

As atualizações trazem novos fluxos, correções e instruções melhores para seu agente. Vale conferir se há uma versão nova de tempos em tempos.

O cabeçalho indica quando há uma atualização disponível. No Pinokio, espere as tarefas terminarem e use **Update**. Se você usa o Foundry diretamente no ComfyUI, siga o [guia de instalação manual](../INSTALL.md).

Ao atualizar o Foundry, você também recebe a versão atual da skill que vem com ele. **Se você copiou a skill para a pasta de habilidades do seu agente, atualize essa cópia também.**

A skill orienta o agente a conferir a versão do aplicativo, as funções disponíveis e possíveis atualizações. Se houver uma versão nova ou uma incompatibilidade, ele deve explicar isso no seu idioma. Os controles anunciados pelo aplicativo em execução são a referência para o que está disponível.

## Hardware, armazenamento e licenças

O Foundry está em **versão preliminar para Windows e NVIDIA**. A máquina de referência usa uma RTX 4080 SUPER, 16 GB de VRAM e 64 GB de RAM. Os requisitos variam conforme o fluxo. O CCORE verifica a memória da GPU e oferece opções mais leves quando necessário.

Em Configurações, você pode gerenciar os modelos instalados e conferir os arquivos temporários antes de limpar o cache. Os modelos publicados necessários para um fluxo podem ser baixados de novo.

O código original do Foundry usa a licença **Apache-2.0**. Modelos, pesos e ferramentas de terceiros têm seus próprios termos. Consulte os [avisos de terceiros](../THIRD-PARTY.md), especialmente antes de usar um resultado comercialmente.

## Um projeto que cresce com a comunidade

O Foundry se apoia no trabalho de pesquisadores, autores de modelos e criadores de fluxos. Obrigado às equipes e comunidades por trás de Pixal3D, TRELLIS.2, Hi3D, Idol, HairDeck, CCORE, Garment Particles, Qwen, FLUX, MoGe, MiniMax H3, ComfyUI e Blender.

A seção **Sobre** reúne os créditos e agradece a quem contribuiu. Sugestões de fluxos, relatos de bugs, correções de tradução e pull requests são bem-vindos.

- [Relatar um problema ou sugerir um fluxo](https://github.com/mumblebox-gpt/mumblebox-foundry/issues)
- [Configurar o MCP e a skill](AGENT-SETUP.md)
- [Contribuir com traduções](LOCALIZATION.md)
- [Dependências e ambientes](../dependencies.json)
- [Verificações e limitações conhecidas](RELEASE-VALIDATION.md)
- [Outros projetos da Mumblebox](https://github.com/mumblebox-gpt?tab=repositories)

O roteiro no aplicativo mostra as ideias para as próximas versões. As versões publicadas mostram o que já está disponível para instalar.
