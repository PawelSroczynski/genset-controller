#!/usr/bin/env python3
"""Inject the YAML sources into index.html.

index.html must work from file:// with no server, so both machine definitions
are embedded in <script type="text/yaml"> blocks rather than fetched. That makes
the embedded copy a duplicate of the file on disk, and a duplicate goes stale:
editing hybrid-skeleton.yaml and forgetting this step once left the page
rendering an empty diagram, because the embedded copy had no `coupling:` section.

Run this after touching either YAML. It is idempotent and reports what changed.
"""
import io, re, sys, hashlib

# hybrid-skeleton.yaml NIE jest już osadzany: widok współdziałania został zdjęty.
# Plik zostaje jako dokument projektowy i link w stopce.
PARY = [('defaultYaml', 'state-machine.yaml'),
        ('plantYaml', 'plant.yaml')]

def main():
    s = io.open('index.html', encoding='utf-8').read()
    przed = s
    for blok, plik in PARY:
        tresc = io.open(plik, encoding='utf-8').read().strip()
        if '</script>' in tresc:
            sys.exit('BLAD: %s zawiera </script>, nie da sie osadzic' % plik)
        # [^<] w treści: bez tego pusty blok dociąga do zamknięcia NASTĘPNEGO
        # bloku i go połyka. Zdarzyło się raz i skasowało cały szkielet hybrydy.
        wzor = re.compile(r'(<script id="%s" type="text/yaml">\n)((?:(?!</script>).)*?)(\n</script>)' % blok, re.S)
        if not wzor.search(s):
            sys.exit('BLAD: nie znalazlem bloku %s w index.html' % blok)
        stare = wzor.search(s).group(0)
        s = wzor.sub(lambda m: m.group(1) + tresc + m.group(3), s, count=1)
        nowe = wzor.search(s).group(0)
        stan = 'bez zmian' if stare == nowe else 'ZAKTUALIZOWANY'
        print('  %-14s <- %-22s %s  (%d B)' % (blok, plik, stan, len(tresc)))
    if s != przed:
        io.open('index.html', 'w', encoding='utf-8').write(s)
        print('index.html zapisany, %d B' % len(s))
    else:
        print('index.html bez zmian')

if __name__ == '__main__':
    main()
