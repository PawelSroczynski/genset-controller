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

  Clickick_switch.ogg              Public domain, autor: stephan
  https://commons.wikimedia.org/wiki/File:Clickick_switch.ogg
  -> trzaśnięcie styków, zasysanie zwory i odpadnięcie

Dipswitch_on_off.ogg, użyty wcześniej na przekaźniki, wyleciał po pomiarze:
**zero energii poniżej 1,5 kHz** (7,7% w 1,5-4 k, resztę powyżej). Dlatego
brzmiał jak tyknięcie, nie jak styk. Clickick ma 16-23% w 200-600 Hz i tyle
samo w 0,6-1,5 kHz, czyli pudło, które słychać w szafie, plus ogon pomieszczenia
schodzący do -35 dB po 70 ms.

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
 'click':'https://upload.wikimedia.org/wikipedia/commons/8/8e/Clickick_switch.ogg',
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

def wyrownaj_dryf(x, ramka_ms=50):
    """Zdejmuje wolny dryf poziomu. Regresja liniowa na obwiedni w dB
    i odwrotna poprawka — samo nachylenie, bez przesunięcia, więc średni
    poziom zostaje.

    Po co: nagranie silnika cichnie po zaskoku, obroty się układają. Pętla
    z surowego wycinka ma przez to rampę w dół i po sklejeniu słychać, gdzie
    się zaczyna — głośniej na początku, ciszej na końcu. Poprawka jest LINIĄ,
    nie obwiednią chwilową: obwiednia chwilowa skasowałaby wybuchy, czyli to,
    co w silniku jest sygnałem, a nie błędem."""
    h = int(SR*ramka_ms/1000.0)
    n = max(2, len(x)//h)
    db = np.array([20*np.log10(np.sqrt(np.mean(x[i*h:(i+1)*h]**2)) + 1e-9)
                   for i in range(n)])
    t = np.arange(n)
    nachylenie = np.polyfit(t, db, 1)[0]
    g = 10**(-(nachylenie*t)/20.0)
    return x*np.interp(np.arange(len(x)), (t+0.5)*h, g)

def petla(x, zakladka_ms=150):
    """Pętla z przenikaniem. Nagranie nie zapętla się samo: koniec i początek
    nie pasują do siebie i słychać to jako klik przy każdym obrocie. Ogon
    przenika się z początkiem krzywą równej mocy, więc szew znika, a głośność
    w miejscu sklejenia nie siada.

    Dryf zdejmowany PRZED przenikaniem. Przenikanie samo zszywa tylko 150 ms
    na styku — rampy rozciągniętej na dwie sekundy nie widzi, a to ją właśnie
    słychać jako „inny początek i koniec"."""
    x = wyrownaj_dryf(x)
    o = int(SR*zakladka_ms/1000.0)
    assert len(x) > 2*o, 'wycinek za krótki na zakładkę'
    L = len(x) - o
    out = x[:L].copy()
    t = np.linspace(0, 1, o)
    out[:o] = x[:o]*np.sqrt(t) + x[L:L+o]*np.sqrt(1-t)
    return out

def przytlum_gore(x, f0=8000.0, db=-6.0):
    """Ścina górę o `db` powyżej f0, nie ruszając ataku w średnicy.
    Nagranie pstryczka ma ~30% energii powyżej 10 kHz — to syk mikrofonu,
    nie styk. Filtr jednobiegunowy, bo ostrzejszy dzwoniłby na transjencie."""
    a = np.exp(-2*np.pi*f0/SR)
    lp = np.empty_like(x); y = 0.0
    for i, v in enumerate(x):
        y = (1.0-a)*v + a*y
        lp[i] = y
    return lp + (10**(db/20.0))*(x - lp)

def krawedzie(x, we_ms=1.0, wy_ms=10.0):
    """Wygasza krawędzie wycinka. Narastanie tylko 1 ms, bo atak trzaśnięcia
    siedzi 6 ms od cięcia — 10 ms jak w mp3 zjadłoby mu zbocze."""
    x = x.copy()
    a, b = int(SR*we_ms/1000.0), int(SR*wy_ms/1000.0)
    if len(x) > a+b:
        x[:a] *= np.linspace(0, 1, a); x[-b:] *= np.linspace(1, 0, b)
    return x

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

def zapisz_mp3(nazwa, x, wyc_ms=10, kbps=96):
    k = int(SR*wyc_ms/1000.0)
    if len(x) > 2*k:
        x[:k] *= np.linspace(0,1,k); x[-k:] *= np.linspace(1,0,k)
    sur = os.path.join(KAT, nazwa+'.raw')
    (x*32767).astype('<i2').tofile(sur)
    p = os.path.join(KAT, nazwa+'.mp3')
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','s16le',
                    '-ar',str(SR),'-ac','1','-i',sur,'-codec:a','libmp3lame',
                    '-b:a','%dk'%kbps, p], check=True)
    os.remove(sur)
    return p, len(x)/float(SR)

if __name__ == '__main__':
    os.makedirs(KAT, exist_ok=True)
    auto  = pobierz('auto',  ZRODLA['auto'])
    click = pobierz('click', ZRODLA['click'])

    # Granice wyznaczone z profilu głośności i jasności widma, nie na oko:
    # do 14,5 s krzątanina, 14,9–16,1 kręcenie (jasność ~1,2 kHz), od 16,1
    # zaskok i spadek jasności do ~300 Hz, 17,6–19,6 równy bieg jałowy.
    WYCINKI = [
        # Dwa trzaśnięcia w jednym nagraniu: 0,066 s i 0,210 s (atak z profilu
        # głośności co 2 ms). Cięcie pierwszego kończy się przed 0,20 s, żeby
        # nie wciągnąć drugiego. Odpadnięcie o 1,5 dB ciszej — sprężyna wraca
        # słabiej niż cewka zasysa.
        ('relay-on',     click, 0.060, 0.190, 'click', -1.5),
        ('relay-off',    click, 0.204, 0.340, 'click', -3.0),
        ('engine-start', auto, 14.85, 17.60, 'mp3',   -7.0),
        ('starter',      auto, 14.95, 16.05, 'loop', -10.0),
        # Okno biegu jałowego wybrane POMIAREM, nie na oko: regresja poziomu
        # w ramkach 50 ms po całym nagraniu daje tu dryf 0,0 dB i rozrzut
        # 1,0 dB — najspokojniejszy fragment w całym pliku. Poprzednie okno
        # 17,60–19,75 spadało o 2,7 dB i to był ten słyszalny „początek
        # i koniec" pętli.
        # Długość pętli 1,915 s. Nie jest okrągła i nie ma być: wybrana
        # przemiałem 1,70–2,25 s co 5 ms po KRYTERIUM SŁYSZALNEJ WADY —
        # odstęp wybuchów przechodzący przez szew ma być równy medianie
        # (86,7 ms, czyli obrót wału przy 690 obr/min). Przy 1,915 s błąd
        # wynosi 0,0 ms i trzyma się przy zakładce 20, 30, 40, 60 i 150 ms,
        # więc to zgodność fazy rytmu, a nie przypadek jednego przenikania.
        # Najgorsze długości w tym samym paśmie dają 120–144 ms błędu, czyli
        # kuksaniec co obrót pętli. Do tego 150 ms zakładki: 1,915 + 0,150.
        ('engine',       auto, 18.100, 20.165, 'loop', -12.0),
    ]
    for nazwa, zrodlo, od, do, fmt, db in WYCINKI:
        x = wczytaj(zrodlo, od, do)
        if fmt == 'click':
            # Jednostrzał w WAV i w pełnym 44,1 kHz. Mp3 rozmazuje impuls
            # i gubi na nim ~3 dB szczytu (zmierzone: -3,0 dB przed kodowaniem,
            # -5,9 dBFS po), a 22 kHz obciąłby górę trzaśnięcia. Plik ma 6 kB,
            # więc nie ma czego oszczędzać.
            x = norm(krawedzie(przytlum_gore(x)), db)
            p, dl = zapisz_wav(nazwa, x, sr_out=SR)
        elif fmt == 'loop':
            x = norm(petla(x), db)
            p, dl = zapisz_wav(nazwa, x)
        else:
            x = norm(x, db)
            p, dl = zapisz_mp3(nazwa, x)
        print('  %-13s %5.0f ms  %6d B  %s  z %s' %
              (nazwa, dl*1000, os.path.getsize(p), fmt.upper(), os.path.basename(zrodlo)))
