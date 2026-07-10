# site — Platzhalter-Seite (Sign of Life)

Statische, selbstenthaltene Seite, die je Umgebung ein Lebenszeichen zeigt
(Produktname, Umgebung, R1-Status). Sie leitet die Umgebung aus der Subdomain ab
(`dev.` / `test.` / `int.` → sonst `prod`) — dieselbe `index.html` funktioniert
für alle vier URLs.

Das ist **bewusst keine** interaktive Radar-UI (E1: keine UI vor stabilem
Schema). Sie macht nur den Deploy-Pfad end-to-end sichtbar und wird in einem
späteren Release durch die echte Ansicht ersetzt.

Der Subdomain-Docroot der jeweiligen Umgebung zeigt auf **dieses Verzeichnis**
(`site/`). Der Deploy aktualisiert es per SSH-git-pull (siehe `../deploy/`).
