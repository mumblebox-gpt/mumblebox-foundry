# Mumblebox 3D Asset Foundry

**Version de Foundry 0.1.0-preview.31**

[English](../README.md) · [简体中文](README.zh-CN.md) · [Español (Latinoamérica)](README.es-419.md) · [Français](README.fr.md) · [Português (Brasil)](README.pt-BR.md) · [Deutsch](README.de.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [हिन्दी](README.hi.md)

**Créez des images et des ressources 3D sur votre PC, en solo ou avec votre agent de codage.**

Foundry réunit des flux de travail d’IA dans des assistants guidés, avec des réglages de départ, des aperçus et des résultats que vous pouvez reprendre. Vous pouvez commencer sans connaître ComfyUI. L’installateur Pinokio s’occupe du logiciel et des dépendances. Les graphes restent accessibles si vous voulez régler le traitement plus finement.

Créez des accessoires de jeu, des éléments de personnage, des coiffures, des splats ou des objets pour l’impression 3D. Prenez le temps de vérifier le résultat selon l’usage prévu. Un maillage généré peut demander des retouches, une rétopologie, un ajustement ou une préparation à l’impression.

[Installer avec Pinokio](PINOKIO.md) · [Versions à télécharger](https://github.com/mumblebox-gpt/mumblebox-foundry/releases) · [Connecter un agent](AGENT-SETUP.md) · [Historique des versions](../CHANGELOG.md)

## Projet original et communauté Pinokio

Le projet original, maintenu par **mumblebox-gpt**, est [Mumblebox Foundry sur GitHub](https://github.com/mumblebox-gpt/mumblebox-foundry). Suivez ce dépôt pour le développement en cours et consultez ses [versions publiées](https://github.com/mumblebox-gpt/mumblebox-foundry/releases) pour les notes de version et les téléchargements disponibles. Si vous lisez un fork ou une copie de ce README, ces liens vous ramènent au projet original ; un fork peut contenir des modifications différentes ou une version plus ancienne.

Nous sommes fiers de créer aux côtés de la communauté de créateurs de [Pinokio](https://pinokio.co/). Pinokio facilite l'installation et le partage d'outils locaux. Nous apprécions cette communauté où les créateurs peuvent découvrir leurs projets respectifs, échanger des retours utiles et apprendre ensemble. Merci à cocktail peanut et à toutes les personnes qui contribuent à cet écosystème créatif. [Retrouvez Foundry sur Pinokio](https://pinokio.co/apps/github-com-mumblebox-gpt-mumblebox-foundry).

## Donnez une longueur d’avance à votre agent de codage

Demandez à votre agent de générer une première version dans Foundry, puis reprenez ensemble le résultat dans Blender ou un autre éditeur 3D.

- **Le MCP donne accès aux outils de Foundry.** L’agent peut découvrir les flux de travail et leurs réglages, lancer des tâches, suivre leur progression, consulter les aperçus et récupérer les exports. Il utilise les mêmes services que l’interface.
- **La compétence compagnon guide l’agent.** Elle l’aide à choisir le bon flux, à respecter les images et consignes fournies ainsi que les limites de mémoire, puis à vérifier et à transférer le résultat.
- **La génération tourne sur votre machine.** Votre agent peut avancer sur d’autres tâches pendant le calcul. Vous pouvez regarder les résultats dans l’assistant et reprendre le même travail enregistré.

Le but est de gagner du temps, d’économiser des tokens et d’éviter de refaire les mêmes étapes de modélisation à la main. Le gain dépend de l’objet, du flux choisi et du travail de finition. La compétence évolue au fil des projets et des retours de la communauté. [Guide du MCP et de la compétence compagnon](AGENT-SETUP.md)

## Choisissez un flux de travail

| Flux de travail | Ce qu’il produit | Quand le choisir |
| --- | --- | --- |
| **Image unique ou texte** | Pixal3D crée la géométrie à partir d’une image. Hi3D affine le maillage, puis Foundry le nettoie et TRELLIS.2 ajoute les textures. Vous pouvez aussi créer l’image à partir d’un texte dans l’assistant. | Pour aller directement au maillage avec moins d’étapes et de modèles. Essayez une image nette de trois quarts. |
| **Vues multiples** | Générez et vérifiez quatre vues avec les modèles Qwen ou FLUX pris en charge. Pixal3D reconstruit le maillage, puis Hi3D et TRELLIS.2 assurent la finition. | Les humanoïdes sont un bon point de départ. Les réglages pour les véhicules, les accessoires et les créatures sont encore en cours d’amélioration. |
| **Guidage 3D** | Combinez une géométrie provisoire Pixal3D, des vues mesurées dans Blender, des estimations MoGe 2 et le guidage Qwen avant la reconstruction. | Pour les objets dont vous voulez choisir et vérifier les angles de prise de vue. Prévoyez davantage de calcul. |
| **Splat et solide** | Obtenez un splat gaussien avec Idol de Sperid Labs et un maillage compagnon nettoyé. Vous pouvez affiner le maillage avec Hi3D. | Pour conserver une apparence détaillée tout en gardant une géométrie plus légère. L’assistant propose une vidéo orbitale et une comparaison des maillages. |
| **De l’orbite au maillage** | Créez une vidéo orbitale H3 à partir d’une image, choisissez des vues alignées, puis reconstruisez avec Pixal3D. Hi3D et TRELLIS.2 assurent la finition. | Pour vérifier les angles et écarter une vue floue ou déformée avant la reconstruction. |
| **Orbite et splats gaussiens** | Créez un maillage texturé et un splat gaussien aligné à partir d’une même vidéo. Comparez-les avec des caméras liées et exportez la paire ou un MP4 hybride. | Pour garder un maillage modifiable et des détails qui varient selon le point de vue. |
| **Plateau tournant virtuel** | Produisez une vidéo orbitale avec H3, puis reconstruisez le sujet par photogrammétrie avec Meshroom ou COLMAP + OpenMVS. | Pour essayer une reconstruction par photogrammétrie à partir d’une orbite cohérente. |
| **CCORE Texte** | Décrivez un accessoire stylisé. L’assistant propose 12 exemples modifiables, une amélioration facultative du texte avec Qwen, un aperçu 3D et un export GLB. | Pour des outils, du mobilier ou des accessoires de jeu individuels. |
| **CCORE Image + texte** | Donnez une image et une description. CCORE utilise son projecteur visuel pour interpréter l’image. Vous pouvez créer la référence dans l’assistant. | Pour reprendre ou modifier des éléments d’une photo, d’un croquis ou d’un rendu. |
| **HairDeck** | Cartes de cheveux, variantes, planches d’aperçu, ajustement, matériaux, chaînes dynamiques facultatives, aperçu du mouvement et exports GLB ou VRM. | Pour une coiffure bien visible sur l’image de référence. Le flux utilise HairDeck et l’intégration ComfyUI de FengLairh. |
| **Garment Particles · expérimental** | Créez et modifiez des vêtements avec les outils des auteurs. Obtenez des patrons de couture, préparez le maillage et essayez le drapé dans Blender. | Pour explorer des modèles de vêtements. Vérifiez l’ajustement et la déformation sur le personnage et prévoyez des retouches. |
| **Créer des images** | Créez une image ou une paire face/dos, retouchez le résultat, utilisez des LoRA compatibles et retrouvez vos images dans la galerie. | Pour préparer une référence ou conserver l’image elle-même. |

Chaque flux a son propre assistant et sa propre section dans le graphe. Les cartes **À venir** présentent des idées encore en développement.

## Lancez votre premier projet

1. Installez [Pinokio](https://pinokio.co/) et suivez le [guide d’installation de Foundry](PINOKIO.md) pour ajouter le dépôt.
2. Choisissez **Install**, puis **Start Foundry** et **Open Foundry**.
3. Ouvrez **Image unique ou texte**. Importez ou déposez une image, prenez une photo avec votre webcam, choisissez une image dans la galerie ou créez-la à partir d’une description.
4. Regardez les aperçus et choisissez les fichiers à exporter. **Rocket Mode** peut enchaîner les étapes sélectionnées en passant les vérifications facultatives.

Si vous utilisez déjà ComfyUI, suivez [l’installation manuelle](../INSTALL.md), puis ouvrez `Mumblebox 3D Asset Foundry.json`. L’installation prépare le logiciel. Les poids manquants sont récupérés au premier lancement du flux qui en a besoin. Prévoyez de la place pour les modèles, les fichiers de travail et les exports.

## Vérifiez et exportez le résultat

Selon le flux, vous pouvez exporter en GLB, FBX, OBJ, BLEND, STL ou SPZ et obtenir des textures, des aperçus ou une archive ZIP. Les maillages détaillés et allégés peuvent inclure des UV et des textures précalculées.

**Les quadrilatères modifiables sont facultatifs.** Image unique et Vues multiples proposent QuadriFlow et Instant Meshes sur CPU, ou CyberRemesher sur GPU NVIDIA avec CUDA. L’assistant explique les réglages avancés. QuadriFlow peut mobiliser fortement le CPU et prendre du temps. Vous pouvez garder les triangles et obtenir un maillage texturé. Les aperçus GLB utilisent des triangles. Les formats d’édition compatibles conservent les faces à quatre côtés.

Vérifiez les déformations, la géométrie d’impression ou de collision et les matériaux dans votre outil final. HairDeck peut produire un GLB statique ou un VRM équipé d’os dynamiques. La vidéo montre le mouvement des cheveux. Avec Garment Particles, l’ajustement au personnage et le drapé restent expérimentaux.

Les archives rassemblent les fichiers choisis, un README, les mesures, les sommes de contrôle, la provenance et les notices applicables. Les images de référence privées, les textes saisis et les fichiers de travail restent hors des archives standard. L’historique permet de retrouver les exports. Dans **Historique → Vidéos**, vous pouvez lire, télécharger ou supprimer les vidéos enregistrées séparément.

## Langue et accessibilité

Choisissez la langue dans l’en-tête ou dans les paramètres. L’interface se met à jour sur place et conserve votre texte, vos références, vos aperçus et vos tâches en cours.

La langue d’une consigne de génération dépend du modèle que vous utilisez. Foundry conserve vos consignes telles que vous les saisissez.

L’auteur de CCORE recommande les consignes en anglais. Les 12 exemples intégrés suivent la langue de l’interface. Le bouton **Traduire en anglais** utilise le modèle Qwen local. Relisez le texte avant de lancer la génération. Q4 est le réglage de départ recommandé et demande moins de mémoire vidéo. Q8 utilise une précision numérique supérieure. La traduction exige que le modèle tienne en mémoire GPU et conserve votre texte si le chargement échoue. **Améliorer la description** sert à retravailler le texte de façon créative.

Choisissez un thème clair ou sombre avec **Thème**. Le menu **Taille du texte** propose la taille par défaut, 112 %, 125 %, 150 %, 175 % et 200 %. Ouvrez les réglages avancés quand vous en avez besoin.

## Gardez Foundry et la compétence à jour

Les nouvelles versions peuvent apporter des flux, des corrections et de meilleurs conseils pour les agents. Pensez à vérifier les mises à jour de temps en temps.

L’en-tête indique si une version est disponible. Dans Pinokio, attendez la fin des tâches en cours et utilisez **Update**. Si vous utilisez Foundry directement dans ComfyUI, suivez le [guide d’installation manuelle](../INSTALL.md).

Une mise à jour de Foundry met aussi à jour la compétence livrée avec l’application. **Si vous l’avez copiée dans le dossier de compétences de votre agent, mettez aussi cette copie à jour.**

La compétence demande à l’agent de vérifier la version de l’application, les fonctions disponibles et les mises à jour. Si une incompatibilité ou une mise à jour est détectée, l’agent doit l’expliquer dans votre langue. Les options annoncées par l’application en cours d’exécution font foi.

## Matériel, stockage et licences

Foundry est en **version d’aperçu pour Windows et NVIDIA**. La machine de référence dispose d’une RTX 4080 SUPER, de 16 Go de VRAM et de 64 Go de RAM. Les besoins varient selon le flux. CCORE vérifie la mémoire GPU et propose des réglages plus légers si nécessaire.

Dans les paramètres, vous pouvez gérer les modèles installés et examiner les fichiers temporaires avant de vider le cache. Les modèles publiés dont un flux a besoin peuvent être récupérés à nouveau.

Le code original de Foundry est sous licence **Apache-2.0**. Les modèles, les poids et les outils tiers ont leurs propres conditions. Consultez les [notices tierces](../THIRD-PARTY.md), notamment avant tout usage commercial.

## Un projet qui grandit avec la communauté

Foundry s’appuie sur le travail de chercheurs, d’auteurs de modèles et de créateurs de flux. Merci aux équipes et communautés derrière Pixal3D, TRELLIS.2, Hi3D, Idol, HairDeck, CCORE, Garment Particles, Qwen, FLUX, MoGe, MiniMax H3, ComfyUI et Blender.

La section **À propos** présente les crédits et remercie les personnes qui ont contribué. Vos idées de flux, rapports de bugs, corrections de traduction et pull requests sont les bienvenus.

- [Signaler un problème ou proposer un flux de travail](https://github.com/mumblebox-gpt/mumblebox-foundry/issues)
- [Configurer le MCP et la compétence](AGENT-SETUP.md)
- [Contribuer aux traductions](LOCALIZATION.md)
- [Dépendances et environnements](../dependencies.json)
- [Vérifications et limites connues](RELEASE-VALIDATION.md)
- [Autres projets Mumblebox](https://github.com/mumblebox-gpt?tab=repositories)

La feuille de route dans l’application présente les idées à venir. Les versions publiées indiquent ce que vous pouvez installer.
