# Anleitung zu Nine Lives

[English](guide.md) · **Deutsch**

Diese Anleitung erklärt einen Tausch Schritt für Schritt und was genau dabei passiert. Einen
kurzen Überblick und die Installation findest du in der [README](../README.de.md).

- [Vor dem Tausch](#vor-dem-tausch)
- [Der Tausch Schritt für Schritt](#der-tausch-schritt-für-schritt)
- [Was genau passiert](#was-genau-passiert)
- [Nach dem Tausch](#nach-dem-tausch)
- [Rückgängig machen](#rückgängig-machen)
- [Typische Fälle](#typische-fälle)
- [Fehlersuche](#fehlersuche)

## Vor dem Tausch

1. **Das neue Gerät koppeln**, wie gewohnt in seiner Integration. Name und Entity-IDs sind
   egal, sie werden beim Tausch ersetzt.
2. **Das alte Gerät am besten in Home Assistant lassen**, bis der Tausch erledigt ist; dann
   lässt er sich rückgängig machen. Ist es schon weg, etwa weil du es zuerst in der App des
   Herstellers gelöscht hast, siehe [Altes Gerät schon gelöscht](#altes-gerät-schon-gelöscht).
3. **Abgesteckt oder kaputt ist kein Problem.** Das alte Gerät darf schon nicht mehr
   erreichbar sein. Bei Zählern nimmt Nine Lives dann den Stand, den die Statistik zuletzt
   erfasst hat.
4. **Ein Backup schadet nicht.** Nine Lives legt für Rückgängig eine eigene Sicherung an,
   aber ein Backup von Home Assistant vor dem ersten Tausch gibt zusätzliche Sicherheit.

## Der Tausch Schritt für Schritt

**Nine Lives** in der Seitenleiste öffnen. Nur Admins sehen es.

### 1. Geräte wählen

Altes und neues Gerät auswählen. Damit man sie auch bei gleichem Namen und Modell
auseinanderhält, zeigt jeder Eintrag:

- Hersteller, Modell, Bereich und Integration,
- wann das Gerät hinzugefügt wurde: **neu, heute 18:46** bei Geräten der letzten sieben Tage,
  sonst **seit** dem Datum. In der Liste für das neue Gerät stehen die jüngsten oben,
- **nicht erreichbar**, wenn das Gerät nicht antwortet, etwa weil es abgesteckt ist.

Wurde das als alt gewählte Gerät nach dem als neu gewählten hinzugefügt, fragt Nine Lives,
ob sie vertauscht sind, und bietet an, sie zu tauschen. Geräte mit Identifizieren-Funktion
(viele Steckdosen und Lampen) bekommen einen Knopf **Identifizieren**: Das Gerät blinkt oder
piept, und du siehst im Raum, welches es ist. Mit dem Filterfeld lässt sich die Liste
eingrenzen.

### 2. Zuordnung prüfen

Nine Lives schlägt vor, welche neue Entität welche alte ersetzt:

- Gepaart werden nur Entitäten desselben Typs (Sensor mit Sensor, Schalter mit Schalter).
- Haben beide eine Geräteklasse, muss sie gleich sein: Eine Temperatur ersetzt nie eine
  Luftfeuchte.
- Hat nur eine von beiden eine Geräteklasse, muss die Einheit passen. So wird zum Beispiel
  die Signalstärke nicht mit der Helligkeit gepaart.
- Unter den übrigen Kandidaten entscheiden gleiche Einheit, Zustandsklasse und Name.

Unter jeder Entität steht ihr aktueller Wert, zum Beispiel `21,3 °C` oder `4,2 W`; so siehst
du, ob die richtigen Sensoren gepaart sind. Jedes Paar lässt sich ändern oder auf
**überspringen** stellen. Übersprungene alte Entitäten
bleiben beim alten Gerät. Neue Entitäten ohne Partner stehen unter der Tabelle; sie behalten
ihre eigenen IDs.

**Neue ID:** Manche alten IDs passen nicht mehr, etwa nachdem ein Gerät umbenannt wurde
(`button.steckdose_anker_identifizieren` an einer Steckdose, die jetzt einen Drucker
versorgt). Wenn in Home Assistant nichts auf so eine ID verweist, bietet Nine Lives die ID an,
die Home Assistant der Entität heute geben würde. Der Haken ist gesetzt; nimm ihn heraus, um
die alte ID zu behalten. Angeboten wird das nur, wenn die alte ID nirgends vorkommt: nicht in
Automationen, Skripten, Szenen, Dashboards, YAML-Dateien, im Energie-Dashboard und nicht in
den Einstellungen anderer Integrationen.

### 3. Vorschau lesen

Die Vorschau zeigt alles, bevor es passiert:

- **Übernommene Entity-IDs:** welche neue Entität unter welcher ID landet.
- **Geräte:** was mit Bereich, Labels und dem alten Gerät geschieht.
- **Umgeschriebene Geräte-Verweise:** jede Stelle in Automationen, Skripten, Szenen und
  Dashboards, an der die ID des alten Geräts ersetzt wird.
- **Bitte danach prüfen:** Geräte-Trigger, -Bedingungen und -Aktionen, die es am neuen Gerät
  vielleicht nicht gibt (siehe [Fernbedienungen und Taster](#fernbedienungen-und-taster)).
- **Bitte von Hand anpassen:** Stellen, die Nine Lives nicht bearbeitet, etwa YAML-Pakete.

### 4. Tauschen

Nach **Geräte tauschen** und der Bestätigung legt Nine Lives zuerst eine Sicherung an und
nimmt dann die Änderungen vor. Das dauert ein, zwei Sekunden.

## Was genau passiert

### Entitäten

Für jedes Paar:

1. Die neue Entität bekommt, was du an der alten eingestellt hast: Name, Icon, Bereich,
   Labels, Aliase für Sprachassistenten und Optionen wie Nachkommastellen, Einheit oder die
   Freigabe für Sprachassistenten.
2. Die alte Entität wird aus dem Entity-Registry entfernt. Home Assistant merkt sie sich als
   gelöschte Entität; das ist für [Rückgängig](#rückgängig-machen) wichtig.
3. Die neue Entität übernimmt die alte Entity-ID.

Weil die ID gleich bleibt, läuft alles, was Entity-IDs verwendet, ohne jede Änderung weiter:
Automationen, Skripte, Dashboards, Templates, Gruppen, Helfer, das Energie-Dashboard.

### Verlauf und Statistik

Der alte Verlauf bleibt unter der Entity-ID, und die neue Entität setzt ihn einfach fort. Im
Verlaufsdiagramm siehst du im Moment des Tauschs eine kurze Lücke. Was das neue Gerät vor dem
Tausch unter seiner eigenen ID aufgezeichnet hat, bleibt dort und wird von der üblichen
Bereinigung von Home Assistant entfernt.

### Zähler

Zähler für Energie, Gas und Wasser führen in der Langzeitstatistik eine laufende Summe. Wenn
der neue Zähler übernimmt, würde Home Assistant den Sprung vom alten zum neuen Zählerstand
mitzählen:

- Ein neuer Zähler deutlich unter dem alten (weniger als 90 %) gilt als zurückgesetzt, sein
  ganzer Stand zählt dann als Verbrauch. Eine gebrauchte Steckdose mit 50 kWh würde deinem
  Energie-Dashboard 50 kWh hinzufügen.
- Ein Zähler über dem alten fügt die Differenz hinzu.

Nine Lives berechnet diesen Sprung nach denselben Regeln und zieht ihn wieder ab. Home
Assistant erstellt die Statistik alle fünf Minuten; die Korrektur folgt direkt, nachdem der
Zeitraum des Tauschs erfasst ist, meist also nach fünf bis sechs Minuten. Bis dahin steht sie
im Panel unter **Zähler-Korrekturen in Arbeit**. Ausstehende Korrekturen überstehen einen
Neustart. Unterschiedliche Einheiten (Wh und kWh) werden umgerechnet.

### Geräte

- Das neue Gerät bekommt den Bereich des alten, falls es noch keinen hat, und zusätzlich zu
  seinen eigenen die Labels des alten.
- Das alte Gerät wird deaktiviert, damit seine übrigen Entitäten Home Assistant nicht
  zumüllen.

### Automationen, Skripte, Szenen und Dashboards

Die meisten Verweise nutzen Entity-IDs und brauchen keine Änderung. Geräte-Trigger,
-Bedingungen und -Aktionen sowie Geräte-Ziele wie „Gerät einschalten“ nutzen dagegen die
Geräte-ID und die interne Registry-ID der Entität. Diese ersetzt Nine Lives:

- in `automations.yaml`, `scripts.yaml` und `scenes.yaml`, den Dateien, die der Editor von
  Home Assistant schreibt; sie werden danach neu geladen,
- in Dashboards, die Home Assistant speichert (alles, was im Dashboard-Editor bearbeitet
  wird).

Nicht bearbeitet werden:

- YAML-Pakete, mit `!include` eingebundene und andere YAML-Dateien: Sie stehen unter
  **Bitte von Hand anpassen**,
- YAML-Dashboards: ebenfalls dort aufgelistet,
- `automations.yaml`, `scripts.yaml` oder `scenes.yaml`, wenn sie `!secret`, `!include` oder
  ähnliche Tags enthalten. Beim Umschreiben landeten die geheimen Werte im Klartext in der
  Datei.

### Benachrichtigung

Nach dem Tausch zeigt Home Assistant eine Benachrichtigung: welches Gerät welches fortführt,
was noch von Hand anzupassen ist und den Hinweis, das alte Gerät zu entfernen. Sie erscheint
in der Systemsprache, Deutsch oder Englisch.

## Nach dem Tausch

1. **Prüfen:** ein, zwei Dashboards und die Automationen ansehen, die das Gerät nutzen. Die
   Stellen unter „Bitte danach prüfen“ lohnen einen Blick.
2. **Von Hand anpassen**, was die Vorschau aufgelistet hat, falls etwas da ist.
3. **Zähler-Korrekturen abwarten**, falls welche anstehen; das Panel zeigt, wann sie kommen.
4. **Das alte Gerät entfernen**, aus seiner Integration (zum Beispiel im Zigbee-Hub oder unter
   Einstellungen → Geräte). Bis dahin lässt sich der Tausch vollständig rückgängig machen.

## Rückgängig machen

Jeder Tausch steht unter **Durchgeführte Gerätetausche**, auch nachdem er rückgängig gemacht
wurde. Ein Klick auf den Eintrag zeigt, was er bewirkt hat: welche Entity-IDs übernommen
wurden (und neue IDs), welche Verweise umgeschrieben wurden, was zur Prüfung markiert oder zum
Anpassen von Hand gemeldet wurde und die Zähler-Korrekturen mit ihrem Stand. Rückgängig
gemachte Tausche zeigen, wann das war.

Tausche, die sich noch rückgängig machen lassen, haben einen Knopf **Rückgängig**.
Rückgängig:

- gibt den neuen Entitäten ihre eigenen IDs und Einstellungen zurück,
- schaltet das alte Gerät wieder ein und stellt seine Entitäten wieder her. Home Assistant
  bringt sie mit ihrer alten Registry-ID und ihren Einstellungen zurück, wenn ihre
  Integration sie neu anlegt,
- dreht die Geräte-Verweise in Automationen, Skripten, Szenen und Dashboards zurück. Hast du
  eine davon nach dem Tausch bearbeitet, bleiben deine Änderungen erhalten, und nur die
  Geräte-Verweise werden zurückgedreht,
- korrigiert die Zähler-Summen erneut, jetzt für den Sprung vom neuen zurück zum alten Zähler,
- blendet die Benachrichtigung aus.

Rückgängig braucht das alte Gerät. Hast du es aus seiner Integration entfernt, könnte es nicht
zurückkommen, deshalb ist der Tausch dann endgültig: Der Eintrag zeigt „altes Gerät entfernt“
und bietet kein Rückgängig mehr an.

## Typische Fälle

### Von Zigbee zu Thread/Matter

Der Klassiker: Ein Sensor an einem Zigbee-Hub oder an ZHA wird durch einen mit Thread
ersetzt. Neuen Sensor koppeln, tauschen, prüfen, dann den alten aus dem Zigbee-Netz
entfernen.

### Defektes Gerät gegen baugleiches

Funktioniert genauso. Das defekte Gerät darf nicht erreichbar sein; es muss nur noch in Home
Assistant stehen.

### Steckdose mit Energiezähler

Überlass es Nine Lives: Schalter, Leistung, Strom und Energie werden gepaart, und das
Energie-Dashboard läuft ohne Sprung weiter. Misst die neue Steckdose mehr (zum Beispiel die
Spannung), behalten diese Entitäten einfach ihre eigenen IDs.

### Altes Gerät schon gelöscht

Eine häufige Reihenfolge: Das alte Gerät wird zuerst in der App oder Bridge des Herstellers
gelöscht, wodurch es auch aus Home Assistant verschwindet. Home Assistant behält seine
Entitäten aber als gelöschte Einträge, mit Entity-IDs und Einstellungen. Unter der Liste der
alten Geräte **„Altes Gerät nicht mehr in der Liste? Aus gelöschten Einträgen übernehmen“**
wählen. Die Liste zeigt dann gelöschte Geräte, deren Entitäten sich noch übernehmen lassen,
mit dem Zeitpunkt des Löschens. Nine Lives erkennt die Entitäten daran, dass sie zusammen mit
ihrem Gerät gelöscht wurden, und zeigt ihren letzten Namen und Wert aus dem Verlauf.

Alles andere läuft wie gewohnt: Die neuen Entitäten übernehmen IDs und Einstellungen,
Geräte-Verweise werden umgeschrieben und Zähler-Summen laufen weiter (ausgehend vom zuletzt
erfassten Stand). Rückgängig machen lässt sich so ein Tausch nicht, weil das alte Gerät nicht
zurückkommen kann.

### Fernbedienungen und Taster

Automationen, die auf einen Tastendruck reagieren, nutzen meist einen Geräte-Trigger wie
„remote_button_short_press“ der alten Integration. Nine Lives richtet den Trigger auf das
neue Gerät aus, markiert ihn aber unter **Bitte danach prüfen**, weil das neue Gerät seine
Tasten vielleicht anders benennt. Öffne die Automation und wähle die Taste bei Bedarf neu.

## Fehlersuche

### Das Panel erscheint nicht

Nach dem Hinzufügen der Integration die Seite im Browser neu laden. Das Panel sehen nur
Admins.

### Eine Automation funktioniert nicht mehr

Sieh in die Benachrichtigung und die Listen der Vorschau: Geräte-Trigger der alten
Integration und YAML-Dateien brauchen Handarbeit. Steht die Automation in einer YAML-Datei,
die Nine Lives nicht bearbeitet hat, ersetze dort die alte Geräte-ID.

### Debug-Log

Debug-Logging für Nine Lives einschalten, den Tausch oder das Rückgängigmachen wiederholen
und das Log an einen
[Fehlerbericht](https://github.com/Schnuecks/ha-nine-lives/issues/new/choose) anhängen:

```yaml
logger:
  logs:
    custom_components.nine_lives: debug
```

### Wo liegt die Sicherung?

Im Speicher von Home Assistant unter `.storage/nine_lives.backups`. Darin stehen die
Einstellungen der alten und neuen Entitäten, die Originaltexte der geänderten Dateien und
Dashboards und die ausstehenden Zähler-Korrekturen. Der Eintrag eines Tauschs bleibt, bis du
ihn rückgängig machst. Bitte die Datei nicht von Hand bearbeiten.
