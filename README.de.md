# MeshMove

[English](README.md) · **Deutsch**

Ein Gerät in Home Assistant ersetzen, ohne Automationen, Dashboards und Verlauf zu
zerstören – zum Beispiel beim Umzug von Sensoren von Zigbee auf Thread/Matter oder wenn
ein defektes Gerät gegen ein neues getauscht wird.

> **Stand:** frühe Entwicklung, noch nicht nutzbar.

## Was es können wird

1. Altes und neues Gerät in einem Panel in der Seitenleiste auswählen.
2. MeshMove ordnet die Entitäten einander zu (nach Domäne, Geräteklasse und Einheit);
   die Paare lassen sich anpassen.
3. Eine Vorschau zeigt jede Stelle, die sich ändert: Automationen, Skripte, Szenen,
   Dashboards, Helfer, Bereich, Labels, Namen und Freigaben für Sprachassistenten.
4. Ausführen: Die neuen Entitäten übernehmen die alten Entity-IDs, alle Verweise werden
   angepasst. Vorher wird eine Sicherung angelegt, ein Klick macht den Tausch rückgängig.

Stellen, die MeshMove nicht sicher ändern kann (YAML-Pakete, `!include`-Dateien,
Geräte-Trigger ohne Gegenstück am neuen Gerät), werden aufgelistet statt stillschweigend
geändert.

## Installation

Noch nicht veröffentlicht. Danach: In [HACS](https://hacs.xyz/) dieses Repository als
benutzerdefiniertes Repository (Typ *Integration*) hinzufügen, MeshMove installieren,
Home Assistant neu starten und die Integration unter **Einstellungen → Geräte & Dienste**
hinzufügen.

## Benutzung

**MeshMove** in der Seitenleiste öffnen (nur für Admins), altes und neues Gerät wählen,
die vorgeschlagene Zuordnung und die Vorschau prüfen, dann tauschen. Die letzten Tausche
stehen darunter und lassen sich rückgängig machen. Wenn alles läuft, das alte Gerät aus
seiner Integration entfernen.

## Lizenz

[MIT](LICENSE)
