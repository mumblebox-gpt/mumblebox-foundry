# Mumblebox 3D Asset Foundry

**Foundry-Version 0.1.0-preview.31**

[English](../README.md) · [简体中文](README.zh-CN.md) · [Español (Latinoamérica)](README.es-419.md) · [Français](README.fr.md) · [Português (Brasil)](README.pt-BR.md) · [Deutsch](README.de.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [हिन्दी](README.hi.md)

**Erstelle Bilder und 3D-Modelle auf deinem PC, allein oder zusammen mit deinem Coding-Agenten.**

Foundry bündelt lokale KI-Workflows in Assistenten mit sinnvollen Voreinstellungen, Vorschauen und gespeicherten Ergebnissen. Du kannst direkt loslegen, auch wenn du ComfyUI noch nicht kennst. Pinokio kümmert sich bei der Installation um die Software und ihre Abhängigkeiten. Für mehr Kontrolle kannst du die Workflows auch als Knotengraph öffnen.

Erstelle Spielobjekte, Teile für Figuren, Haare, Gaussian Splats oder Modelle für den 3D-Druck. Schau dir jedes Ergebnis vor dem Einsatz an. Je nach Zweck kann es nötig sein, das Mesh zu bearbeiten, die Topologie neu aufzubauen, Teile anzupassen oder das Modell für den Druck vorzubereiten.

[Mit Pinokio installieren](PINOKIO.md) · [Veröffentlichte Downloads](https://github.com/mumblebox-gpt/mumblebox-foundry/releases) · [Coding-Agent verbinden](AGENT-SETUP.md) · [Änderungen](../CHANGELOG.md)

## Das Projekt und die Pinokio-Community

Das Originalprojekt wird von **mumblebox-gpt** auf GitHub gepflegt. Dort findest du aktuelle Änderungen, Versionshinweise und Downloads. Auch wenn du diese Anleitung in einem Fork liest, führen dich diese Links zum Original. [Projekt auf GitHub](https://github.com/mumblebox-gpt/mumblebox-foundry) · [Veröffentlichte Versionen](https://github.com/mumblebox-gpt/mumblebox-foundry/releases)

Pinokio macht es leichter, lokale Tools zu installieren und zu teilen. Danke an cocktail peanut und alle, die ihre Projekte, Rückmeldungen und Erfahrungen in der Community teilen. [Foundry auf Pinokio](https://pinokio.co/apps/github-com-mumblebox-gpt-mumblebox-foundry)

## Gib deinem Coding-Agenten einen guten Startpunkt

Bitte deinen Agenten, mit Foundry ein erstes Modell zu erstellen. Danach könnt ihr es gemeinsam in Blender oder einem anderen 3D-Editor weiterbearbeiten.

- **MCP stellt dem Agenten Werkzeuge zur Verfügung.** Er kann Workflows und Einstellungen finden, Aufträge starten, den Fortschritt verfolgen, Vorschauen prüfen und Exporte abholen. Dafür nutzt er dieselben Dienste wie die Oberfläche.
- **Der mitgelieferte Skill gibt Orientierung.** Er hilft bei der Auswahl eines Workflows, beim Prüfen von Eingaben und Speicherbedarf und bei der Übergabe an das nächste Tool.
- **Die Generierung läuft lokal.** Während Foundry rechnet, kann der Agent an einer anderen Aufgabe weiterarbeiten. Du kannst dasselbe gespeicherte Ergebnis im Assistenten öffnen und selbst prüfen.

So können dein Agent und du Zeit bei wiederkehrenden Modellieraufgaben sparen und mit weniger Agenten-Tokens auskommen. Wie viel das bringt, hängt vom Modell, dem Workflow und der nötigen Nacharbeit ab. [MCP und Skill einrichten](AGENT-SETUP.md)

## Welcher Workflow passt zu deinem Projekt?

| Workflow | Ergebnis | Wann er passt |
| --- | --- | --- |
| **Einzelbild oder Text** | Pixal3D baut ein Mesh aus einem Bild. Hi3D verfeinert es, anschließend folgen Bereinigung, Texturen mit TRELLIS.2 und die gewählten Exporte. Bei Bedarf kannst du das Bild direkt aus Text erstellen. | Der direkte Weg mit wenigen Schritten. Probiere ein klares Bild aus der Dreiviertelansicht. |
| **Rundumansichten** | Erstelle vier Ansichten mit einem unterstützten Qwen- oder FLUX-Modell und prüfe sie vor der Rekonstruktion. Pixal3D, Hi3D und TRELLIS.2 übernehmen den Rest. | Ein guter Start für menschenähnliche Figuren. Die Einstellungen für Fahrzeuge, Einzelobjekte und Kreaturen werden noch verbessert. |
| **3D-geführt** | Ein Pixal3D-Entwurf, gemessene Ansichten aus Blender, MoGe-2-Schätzungen und Qwen helfen bei der Rekonstruktion. | Für Objekte, bei denen du die Kamerawinkel bewusst auswählen und prüfen möchtest. Dieser Workflow braucht mehr Verarbeitung. |
| **Splat und Volumenkörper** | Idol von Sperid Labs erstellt einen Gaussian Splat. Dazu kommt ein separates, bereinigtes Mesh mit optionaler Hi3D-Verfeinerung. | Wenn du viele sichtbare Details und zugleich eine leichtere Geometrie brauchst. |
| **Orbit zu Mesh** | Erstelle ein Rundumvideo mit H3, prüfe die ausgerichteten Einzelbilder und erstelle daraus ein Pixal3D-Mesh. Hi3D und TRELLIS.2 übernehmen die Nachbearbeitung. | Wenn du die Blickwinkel prüfen und schwache Einzelbilder abwählen möchtest. |
| **Orbit mit Splats** | Erstelle ein texturiertes Mesh und einen ausgerichteten Gaussian Splat aus demselben Rundumvideo. Vergleiche beide mit gekoppelten Kameras und exportiere das Paar oder ein Hybridvideo. | Wenn du ein bearbeitbares Mesh und blickwinkelabhängige Details brauchst. |
| **Virtueller Drehteller** | Rekonstruiere ein mit H3 erzeugtes Rundumvideo mit Meshroom oder COLMAP + OpenMVS. | Wenn du Fotogrammetrie mit einem möglichst gleichmäßigen Rundumvideo ausprobieren willst. |
| **CCORE Text** | Ein stilisiertes Spielobjekt aus einer Beschreibung, mit zwölf bearbeitbaren Beispielen, optionaler Qwen-Überarbeitung, 3D-Vorschau und GLB-Export. | Für einzelne Objekte wie Werkzeuge oder Möbel. |
| **CCORE Bild und Text** | CCORE nutzt ein Bild und eine Beschreibung. Bei Bedarf kannst du das Referenzbild im Assistenten erstellen. | Wenn du Merkmale aus einem Foto, einer Skizze oder einem Rendering übernehmen oder verändern möchtest. |
| **HairDeck** | Haarsträhnen aus Hair Cards, Varianten, Anpassung, Materialien, optionale Federknochen, Bewegungsvorschau und ausgewählte GLB- oder VRM-Exporte. | Für klare Frisurvorlagen. Mit HairDeck und FengLairhs ComfyUI-Integration. |
| **Garment Particles (experimentell)** | Kleidung erstellen und bearbeiten, Schnittmuster und Mesh vorbereiten und das Kleidungsstück versuchsweise in Blender an eine Figur anpassen. | Zum Ausprobieren von Entwürfen. Prüfe Passform und Verformung sorgfältig. |
| **Bilder erstellen** | Einzelbilder oder Vorder- und Rückansichten, Bearbeitung, passende LoRAs und eine Galerie. | Für Referenzbilder oder Bilder, die du eigenständig verwenden willst. |

Jeder Workflow hat einen eigenen Assistenten und einen eigenen Bereich im Knotengraphen. Karten mit **Kommt bald** zeigen geplante Funktionen.

## So legst du los

1. Installiere [Pinokio](https://pinokio.co/) und füge das Repository über die [Foundry-Installationsanleitung](PINOKIO.md) hinzu.
2. Wähle **Install**, dann **Start Foundry** und **Open Foundry**.
3. Öffne **Einzelbild oder Text**. Lade ein Bild hoch, ziehe es ins Fenster, nutze deine Webcam oder wähle ein Bild aus der Galerie. Du kannst auch direkt ein Bild aus einer Beschreibung erstellen.
4. Prüfe die Vorschauen und wähle deine Ausgaben. Im **Rocket Mode** läuft Foundry durch die restlichen gewählten Schritte, ohne an optionalen Kontrollpunkten anzuhalten.

Falls du ComfyUI schon installiert hast, folge der [manuellen Anleitung](../INSTALL.md) und öffne anschließend `Mumblebox 3D Asset Foundry.json`. Bei der Installation wird die Software eingerichtet. Fehlende Modellgewichte lädt der gewählte Workflow beim ersten Einsatz. Plane Platz für Modelle, Arbeitsdateien und Ergebnisse ein.

## Vorschau und Export

Welche Ausgaben verfügbar sind, hängt vom Workflow ab. Die Assistenten bieten passende Formate wie GLB, FBX, OBJ, BLEND, STL, SPZ, Texturen, Vorschauen und ZIP-Pakete. Detaillierte und reduzierte Meshes können UVs und gebackene Texturen enthalten.

**Quads sind optional.** Bei Einzelbild und Rundumansichten laufen QuadriFlow und Instant Meshes auf der CPU, CyberRemesher auf NVIDIA CUDA. Hinweise und weitere Einstellungen findest du im Assistenten. Mögliche CPU-Spitzen bei QuadriFlow sind normal. Wenn Quads ausgeschaltet sind, erhältst du weiterhin texturierte Meshes aus Dreiecken. GLB-Vorschauen verwenden Dreiecke. Geeignete Bearbeitungsformate können Quads erhalten.

Prüfe die Topologie für Animationen, die Geometrie für Druck und Kollision und die Materialien im Zielprogramm. HairDeck bietet ein statisches GLB und ein VRM mit Federknochen. In der Drehvorschau siehst du, wie sich die Haare bewegen. Garment Particles ist vor allem bei Passform und Stoffsimulation noch experimentell.

Pakete enthalten die gewählten Dateien, eine README, Messwerte, Prüfsummen, Angaben zur Herkunft und die passenden Hinweise. Normale Pakete lassen private Referenzbilder, Prompts und Arbeitsdateien weg. Im **Verlauf** findest du gespeicherte Ergebnisse. Unter **Verlauf → Videos** kannst du separat gespeicherte Clips ansehen, herunterladen oder löschen.

## Sprache und Lesbarkeit

Wähle die Sprache oben im Fenster oder in den Einstellungen. Die Oberfläche lädt die Texte aus lokalen Sprachdateien und wechselt direkt. Eingaben, Referenzen, Vorschauen und laufende Aufträge bleiben erhalten.

Die Sprachwahl der Oberfläche bestimmt nicht die Sprache deiner Prompts. Foundry übernimmt deine Texte und Modellanweisungen so, wie du sie eingibst. Orientiere dich bei der Prompt-Sprache an der Empfehlung des jeweiligen Modells.

Für CCORE empfiehlt der Autor Prompts auf Englisch. Die integrierten Beispiele folgen der Sprache der Oberfläche. Mit **Ins Englische übersetzen** kannst du einen Entwurf vom lokalen Qwen-Helfer übersetzen lassen und vor dem Start prüfen. Q4 braucht weniger Grafikspeicher und ist ein guter Einstieg. Q8 arbeitet mit höherer numerischer Genauigkeit, was keine bessere Übersetzung garantiert. Das Modell muss vollständig in den Grafikspeicher passen. Falls es nicht passt, bleibt dein Entwurf erhalten. **Beschreibung verbessern** ist eine eigene Funktion und darf kreativ ergänzen.

Unter **Design** kannst du zwischen hell und dunkel wechseln. Über **Schriftgröße** stehen Standard, 112 %, 125 %, 150 %, 175 % und 200 % zur Auswahl.

## Foundry und den Skill aktuell halten

Neue Versionen bringen neue Workflows, Fehlerkorrekturen und bessere Hinweise für Coding-Agenten. Ob ein Update verfügbar ist, siehst du oben im Fenster. Beende in Pinokio zuerst laufende Arbeiten und wähle dann **Update**. Für eine eigenständige ComfyUI-Installation gilt die [manuelle Anleitung](../INSTALL.md).

Beim Aktualisieren von Foundry wird der mitgelieferte Skill mit aktualisiert. Falls du ihn in den Skill-Ordner deines Agenten kopiert hast, aktualisiere diese Kopie separat. Der Skill weist den Agenten an, die Version und die Funktionen der laufenden App, die Kompatibilität und verfügbare Updates zu prüfen. Der Agent kann dir Hinweise dazu in deiner Sprache geben.

## Hardware, Speicherplatz und Lizenzen

Dies ist eine **Vorschau für Windows und NVIDIA**. Als Referenz dient ein PC mit RTX 4080 SUPER, 16 GB Grafikspeicher und 64 GB Arbeitsspeicher. Der Bedarf hängt vom Workflow ab. CCORE prüft den verfügbaren Grafikspeicher und bietet kleinere Einstellungen an, wenn deine Auswahl nicht hineinpasst.

In den Einstellungen kannst du installierte Modelle verwalten und den Cache leeren. Prüfe die angezeigten Dateien vor dem Löschen. Verfügbare Modellgewichte werden bei Bedarf erneut bezogen.

Der eigene Foundry-Code steht unter **Apache-2.0**. Modelle, Gewichte und andere Tools haben ihre eigenen Bedingungen. [Hinweise zu Drittanbietern und kommerzieller Nutzung](../THIRD-PARTY.md)

## Gemeinsam weiterentwickeln

Foundry verbindet die Arbeit von Forschenden und Menschen, die Modelle und Workflows entwickeln. Danke an die Teams hinter Pixal3D, TRELLIS.2, Hi3D, Idol, HairDeck, CCORE, Garment Particles, Qwen, FLUX, MoGe, ComfyUI, Blender und an alle, die Integrationen beitragen.

Unter **Über Foundry** findest du Modellnachweise und ein Dankeschön an Mitwirkende. Vorschläge für Workflows, Fehlerberichte, Übersetzungskorrekturen und Pull Requests sind willkommen.

- [Fehler melden oder einen Workflow vorschlagen](https://github.com/mumblebox-gpt/mumblebox-foundry/issues)
- [Coding-Agent einrichten](AGENT-SETUP.md)
- [Bei Übersetzungen mithelfen](LOCALIZATION.md)
- [Abhängigkeiten](../dependencies.json)
- [Was geprüft wurde](RELEASE-VALIDATION.md)
- [Weitere Mumblebox-Projekte](https://github.com/mumblebox-gpt?tab=repositories)

Die Roadmap in der App zeigt, was geplant ist. Zum Installieren stehen die veröffentlichten Versionen bereit.
