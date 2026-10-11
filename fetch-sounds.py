#!/usr/bin/env python3
"""Pobiera i tnie dźwięki maszyn z nagrań w DOMENIE PUBLICZNEJ.

Dlaczego nie synteza: rozrusznik i silnik mają charakter, którego nie da się
wiarygodnie policzyć — nierówność sprężania, rezonans komory silnika, tło.
Dzwonki interfejsu zostają syntezowane (gen-sounds.py), bo tam synteza jest
lepsza: są powtarzalne i nie niosą cudzego nagrania.

ŹRÓDŁA I LICENCJE — sprawdzone przez API Commons, nie z opisu na stronie:

  Starting_a_car_and_driving.ogg   Public domain, autor: stephan
  https://commons.wikimedia.org/wiki/File:Starting_a_car_and_driving.ogg
  -> rozrusznik, rozruch z zaskokiem, bieg jałowy

  Dipswitch_on_off.ogg             Public domain, autor: stephan
  https://commons.wikimedia.org/wiki/File:Dipswitch_on_off.ogg
  -> zatrzaski przekaźnika, załączenie i odpadnięcie

Domena publiczna, a nie CC BY-SA, wybrana świadomie: te pliki idą do
publicznego repozytorium i na cudzą domenę, więc nie mogą ciągnąć za sobą
obowiązku atrybucji ani klauzuli zaraźliwej.
"""
import numpy as np, subprocess, os, sys, urllib.request, wave

SR = 44100
KAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')
TMP = os.path.join(KAT, '.zrodla')
UA  = 'enklava-symulator/1.0 (https://github.com/PawelSroczynski/genset-controller)'

ZRODLA = {
 'auto': 'https://upload.wikimedia.org/wikipedia/commons/e/eb/Starting_a_car_and_driving.ogg',
 'dip':  'https://upload.wikimedia.org/wikipedia/commons/0/00/Dipswitch_on_off.ogg',
}

def pobierz(nazwa, url):
    os.makedirs(TMP, exist_ok=True)
    cel = os.path.join(TMP, nazwa+'.ogg')
    if os.path.exists(cel): return cel
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req) as r, open(cel,'wb') as f:
        f.write(r.read())
    return cel

def wczytaj(plik, od, do):
    """Wycinek jako mono float, przez ffmpeg — bez zależności od bibliotek."""
    sur = subprocess.run(
        ['ffmpeg','-v','error','-ss',str(od),'-t',str(do-od),'-i',plik,
         '-ac','1','-ar',str(SR),'-f','s16le','-'],
        capture_output=True, check=True).stdout
    return np.frombuffer(sur, dtype='<i2').astype(float)/32768.0

def petla(x, zakladka_ms=150):
    """Pętla z przenikaniem. Nagranie nie zapętla się samo: koniec i początek
    nie pasują do siebie i słychać to jako klik przy każdym obrocie. Ogon
    przenika się z początkiem krzywą równej mocy, więc szew znika, a głośność
    w miejscu sklejenia nie siada."""
    o = int(SR*zakladka_ms/1000.0)
    assert len(x) > 2*o, 'wycinek za krótki na zakładkę'
    L = len(x) - o
    out = x[:L].copy()
    t = np.linspace(0, 1, o)
    out[:o] = x[:o]*np.sqrt(t) + x[L:L+o]*np.sqrt(1-t)
    return out

def norm(x, db):
    x = x - np.mean(x)
    return x/(np.max(np.abs(x)) or 1.0)*(10**(db/20.0))

def zapisz_wav(nazwa, x, sr_out=22050):
    n = int(round(len(x)*sr_out/float(SR)))
    xi = np.interp(np.linspace(0, len(x), n, endpoint=False), np.arange(len(x)), x)
    p = os.path.join(KAT, nazwa+'.wav')
    with wave.open(p,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr_out)
        w.writeframes((xi*32767).astype('<i2').tobytes())
    return p, n/float(sr_out)

def zapisz_mp3(nazwa, x, wyc_ms=10):
    k = int(SR*wyc_ms/1000.0)
    if len(x) > 2*k:
        x[:k] *= np.linspace(0,1,k); x[-k:] *= np.linspace(1,0,k)
    sur = os.path.join(KAT, nazwa+'.raw')
    (x*32767).astype('<i2').tofile(sur)
    p = os.path.join(KAT, nazwa+'.mp3')
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','s16le',
                    '-ar',str(SR),'-ac','1','-i',sur,'-codec:a','libmp3lame',
                    '-b:a','96k', p], check=True)
    os.remove(sur)
    return p, len(x)/float(SR)

if __name__ == '__main__':
    os.makedirs(KAT, exist_ok=True)
    auto = pobierz('auto', ZRODLA['auto'])
    dip  = pobierz('dip',  ZRODLA['dip'])

    # Granice wyznaczone z profilu głośności i jasności widma, nie na oko:
    # do 14,5 s krzątanina, 14,9–16,1 kręcenie (jasność ~1,2 kHz), od 16,1
    # zaskok i spadek jasności do ~300 Hz, 17,6–19,6 równy bieg jałowy.
    WYCINKI = [
        ('relay-on',     dip,  0.12, 0.46, 'mp3', -13.0),
        ('relay-off',    dip,  2.00, 2.42, 'mp3', -14.0),
        ('engine-start', auto, 14.85, 17.60, 'mp3', -14.0),
        ('starter',      auto, 14.95, 16.05, 'wav', -17.0),
        ('engine',       auto, 17.60, 19.75, 'wav', -18.0),
    ]
    for nazwa, zrodlo, od, do, fmt, db in WYCINKI:
        x = wczytaj(zrodlo, od, do)
        if fmt == 'wav':
            x = norm(petla(x), db)
            p, dl = zapisz_wav(nazwa, x)
        else:
            x = norm(x, db)
            p, dl = zapisz_mp3(nazwa, x)
        print('  %-13s %5.0f ms  %6d B  %s  z %s' %
              (nazwa, dl*1000, os.path.getsize(p), fmt.upper(), os.path.basename(zrodlo)))
