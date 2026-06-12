# Best-Practices & Richtlinien für Python-Konsolenanwendungen (CLI)

Dieses Dokument dient als Leitfaden und Regelwerk für Entwickler und AI-Agenten, die an dieser Python-Konsolenanwendung arbeiten. Es stellt sicher, dass der Code sauber, wartbar, robust und gut getestet bleibt.

---

## 1. Clean Code & Architektur

Eine gute Konsolenanwendung trennt die Benutzerschnittstelle (CLI-Interaktion) strikt von der Geschäftslogik (Core-Logik).

### Projektstruktur
Wir bevorzugen ein klares `src/`-Layout oder ein flaches Paketlayout mit getrennten Modulen:
- **`cli.py` oder `__main__.py`**: Einstiegspunkt, Argument-Parsing, Konsolen-Ein-/Ausgabe.
- **`core/` oder Kernmodule**: Reine Geschäftslogik, unabhängig von Konsolen-Ausgaben (`print`, `rich` etc.).
- **`utils.js` / `helpers.py`**: Hilfsfunktionen.

```text
projekt/
├── src/
│   └── mein_projekt/
│       ├── __init__.py
│       ├── __main__.py      # Einstiegspunkt
│       ├── cli.py           # CLI-Definition (click/typer/argparse)
│       ├── core.py          # Reine Geschäftslogik
│       └── utils.py         # Hilfsfunktionen
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   └── test_core.py
├── pyproject.toml           # Konfiguration (Ruff, Pytest, Dependency Management)
└── README.md
```

### CLI-Frameworks
Verwende moderne Bibliotheken statt manuellem `sys.argv`-Parsing:
* **[Typer](https://typer.tiangolo.com/)** (Empfohlen für intuitive, typbasierte CLIs) oder **[Click](https://click.palletsprojects.com/)**.
* **[Rich](https://rich.readthedocs.io/)** für ansprechende Konsolen-Ausgaben (Farben, Tabellen, Ladebalken).

### Regeln für sauberen Code (Clean Code)
1. **Separation of Concerns**: Keine `print()`-Statements in der Kernlogik. Verwende dort stattdessen Rückgabewerte, Exceptions oder das Standard-Modul `logging`.
2. **Type Hinting**: Alle Funktionssignaturen müssen konsequent typisiert werden.
   ```python
   def berechne_wert(faktor: float, basis: int = 10) -> float:
       return basis * faktor
   ```
3. **Explizite Fehlerbehandlung**:
   - Fange keine generischen Exceptions (`except Exception:`), es sei denn, sie werden geloggt und das Programm wird kontrolliert beendet.
   - Definiere eigene Exception-Klassen für fachliche Fehler.
   - CLI-Ebene fängt Exceptions ab und gibt verständliche Fehlermeldungen (rot formatiert) aus, anstatt dem Benutzer einen Traceback zu zeigen (außer im `--debug` Modus).
4. **Konfiguration**: Parameter und Pfade sollten über Umgebungsvariablen (z. B. mit `python-dotenv`) oder Konfigurationsdateien (TOML/JSON) konfigurierbar sein, nicht hardcodiert.

---

## 2. Linting & Code-Qualität

Wir setzen automatisierte Tools ein, um Konsistenz und Fehlerfreiheit zu garantieren.

### Ruff (Linter & Formatter)
[Ruff](https://github.com/astral-sh/ruff) ersetzt Flake8, Black, isort und weitere Tools in einer extrem schnellen Go-Implementierung.

Konfiguration in der `pyproject.toml`:
```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle-Fehler
    "W",   # pycodestyle-Warnungen
    "F",   # Pyflakes
    "I",   # isort (Import-Sortierung)
    "C90", # mccabe (Komplexität)
    "B",   # flake8-bugbear
    "UP",  # pyupgrade (Modernere Syntax)
]
ignore = []
```

### Mypy (Statische Typprüfung)
Statische Typisierung verhindert Laufzeitfehler vorab. Mypy sollte streng konfiguriert sein:
```toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_unused_configs = true
```

### Git Pre-Commit Hooks
Nutze `pre-commit`, um Formatierung und Linting vor jedem Commit zu erzwingen:
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [ --fix ]
      - id: ruff-format
```

---

## 3. Testing

Code ohne Tests gilt als fehlerhaft. CLI-Anwendungen erfordern sowohl Unittests für die Logik als auch Integrationstests für das Benutzerinterface.

### Test-Framework
Wir nutzen **[pytest](https://docs.pytest.org/)**.

### Kernregeln fürs Testen
1. **Logik isoliert testen**: Teste die Kernlogik in `core.py` ohne CLI-Aufrufe.
2. **CLI-Interaktion testen**:
   - Nutze `capsys` (Standard in Pytest), um Standard-Output (`stdout`) und Standard-Error (`stderr`) zu überprüfen.
   - Nutze den `CliRunner` (wenn Click/Typer verwendet wird) für einfache Integrationstests.
3. **Mocking**: Externe API-Aufrufe, Dateisystem-Zugriffe oder zeitintensive Prozesse müssen gemockt werden (z. B. mit `unittest.mock` oder `pytest-mock`).

### Test-Beispiele

**CLI-Test mit Click/Typer:**
```python
from click.testing import CliRunner
from mein_projekt.cli import app

def test_cli_greeting():
    runner = CliRunner()
    result = runner.invoke(app, ["--name", "Alice"])
    assert result.exit_code == 0
    assert "Hallo Alice" in result.output
```

**CLI-Test mit Standard `capsys` & `pytest`:**
```python
from mein_projekt.cli import main
import pytest

def test_main_output(capsys):
    # Simuliere Programmablauf
    main(["--version"])
    captured = capsys.readouterr()
    assert "Version 1.0.0" in captured.out
```

---

## 4. Kommentierung & Dokumentation

Code sollte so geschrieben sein, dass er sich weitgehend selbst dokumentiert. Kommentare erklären das **Warum**, nicht das **Was**.

### Docstrings
Jedes Modul, jede Klasse und jede öffentliche Methode/Funktion **muss** einen Docstring im **Google-Style** besitzen.

```python
def datei_einlesen(dateipfad: str, ignorieren_wenn_leer: bool = False) -> list[str]:
    """Liest den Inhalt einer Textdatei zeilenweise ein.

    Args:
        dateipfad: Der absolute oder relative Pfad zur Zieldatei.
        ignorieren_wenn_leer: Wenn True, wird bei einer leeren Datei kein
            Fehler ausgelöst, sondern eine leere Liste zurückgegeben.

    Returns:
        Eine Liste von Strings, die die Zeilen der Datei darstellen.

    Raises:
        FileNotFoundError: Wenn die Datei unter dem angegebenen Pfad nicht existiert.
        ValueError: Wenn die Datei leer ist und `ignorieren_wenn_leer` False ist.
    """
    # Logik hier...
```

### Inline-Kommentare
- Verwende Inline-Kommentare sparsam.
- Beschreibe komplexe Algorithmen oder Designentscheidungen (z. B. *"Warum wurde dieser spezielle Workaround gewählt?"*).
- Vermeide triviale Kommentare wie:
  ```python
  x = x + 1  # Erhöhe x um 1 (NEIN!)
  ```

### Hilfe-Texte im Terminal
Die CLI selbst ist die primäre Dokumentation für den Benutzer.
- Stelle sicher, dass jeder CLI-Befehl und jedes Argument/Option einen aussagekräftigen `help`-Text besitzt.
- Typer/Click generieren daraus automatisch die Hilfe-Seiten (`--help`).

```python
@app.command()
def import_data(
    file_path: Path = typer.Option(..., help="Pfad zur CSV-Datei, die importiert werden soll"),
):
    """Importiert Kunden- und Bestelldaten aus einer CSV-Datei in die lokale Datenbank."""
    pass
```
