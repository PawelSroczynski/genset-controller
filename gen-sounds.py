#!/usr/bin/env python3
"""Generuje dźwięki INTERFEJSU. Dźwięki MASZYN bierze fetch-sounds.py.

Podział jest ostry i celowy: ten skrypt nie wolno uruchamiać po tamtym,
bo nadpisywałby nagrania syntezą. Dlatego nie generuje już rozrusznika,
silnika ani zatrzasków — te mają własne źródło i własny skrypt.

Dźwięki są PROJEKTOWANE, nie znajdowane. Powód jest praktyczny: gotowe nagrania
CC0 do interfejsów to w większości gołe piknięcia, a te pliki trafiają na
publiczne repozytorium i cudzą domenę, więc każda niejasna licencja jest
kłopotem. Generowanie daje też powtarzalność — plik jest wynikiem tego skryptu,
a nie czymś, czego pochodzenia nikt po roku nie odtworzy.

Każdy dźwięk ma koperta z szybkim narastaniem i wykładniczym wybrzmieniem,
szczyptę pogłosu dla ciepła i jest znormalizowany do -14 dBFS, żeby był tłem
w warsztacie, a nie alarmem.
"""
import numpy as np, subprocess, os, sys

SR = 44100
KAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')

def cisza(ms):           return np.zeros(int(SR*ms/1000.0))
def czas(ms):            return np.arange(int(SR*ms/1000.0))/SR

def ton(f, ms, tau_ms, amp=1.0, faza=0.0):
    t = czas(ms)
    return amp*np.sin(2*np.pi*f*t + faza)*np.exp(-t/(tau_ms/1000.0))

def dzwon(f, ms, tau_ms, partiale, amp=1.0):
    """Partiale jako (mnożnik_częstotliwości, waga, mnożnik_tłumienia).
    Wyższe partiale gasną szybciej — tak zachowuje się każde realne ciało."""
    s = np.zeros(int(SR*ms/1000.0))
    for mnoz, waga, tl in partiale:
        s += ton(f*mnoz, ms, tau_ms*tl, waga)
    return amp*s

def trzask(ms, tau_ms, lo, hi, amp=1.0, ziarno=0):
    """Impuls szumu przepuszczony przez pasmo — tak brzmi styk, a nie sinus."""
    rng = np.random.default_rng(ziarno)
    n = int(SR*ms/1000.0)
    x = rng.standard_normal(n)
    widmo = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0/SR)
    maska = ((f >= lo) & (f <= hi)).astype(float)
    # zmiękczone krawędzie pasma, inaczej słychać dzwonienie filtru
    k = max(1, int(len(maska)*0.02))
    maska = np.convolve(maska, np.ones(k)/k, mode='same')
    x = np.fft.irfft(widmo*maska, n)
    t = czas(ms)
    return amp*x*np.exp(-t/(tau_ms/1000.0))

def pasmo(x, lo, hi):
    """Filtr pasmowy przez widmo, z wygładzoną krawędzią — ostra maska dzwoni."""
    n=len(x)
    W=np.fft.rfft(x); f=np.fft.rfftfreq(n, 1.0/SR)
    m=((f>=lo)&(f<=hi)).astype(float)
    k=max(1,int(len(m)*0.02)); m=np.convolve(m, np.ones(k)/k, mode='same')
    return np.fft.irfft(W*m, n)

def silnik_stop(ms=1600):
    """Zapłony rzedną, obroty siadają, na końcu klaknięcie zaworów."""
    n=int(SR*ms/1000.0); out=np.zeros(n)
    rng=np.random.default_rng(37); t0=0.0; f=25.0
    while t0 < ms/1000.0-0.25 and f > 3.0:
        i0=int(t0*SR); dl=int(0.07*SR); seg=np.arange(dl)/SR
        kop=np.exp(-seg/0.016)
        p = pasmo(rng.standard_normal(dl), 50, 800)*kop + np.sin(2*np.pi*86*seg)*kop*0.8
        dost=min(dl, n-i0)
        if dost>0: out[i0:i0+dost] += p[:dost]*(0.9*f/25.0+0.25)
        t0 += 1.0/f
        f *= 0.86
    i0=int((ms/1000.0-0.18)*SR)
    kl=trzask(90, 3.0, 900, 4200, 0.55, 41)
    dost=min(len(kl), n-i0)
    if dost>0: out[i0:i0+dost] += kl[:dost]
    return out

def polacz(*kawalki):
    """Nakłada kawałki (przesunięcie_ms, sygnał) na wspólną oś."""
    dl = max(int(SR*p/1000.0)+len(s) for p, s in kawalki)
    out = np.zeros(dl)
    for p, s in kawalki:
        i = int(SR*p/1000.0)
        out[i:i+len(s)] += s
    return out

def poglos(x, ms=140, mix=0.11, ziarno=7):
    rng = np.random.default_rng(ziarno)
    n = int(SR*ms/1000.0)
    ir = rng.standard_normal(n)*np.exp(-np.arange(n)/(n/4.0))
    ir[0] = 1.0
    moc = np.sqrt(np.sum(ir**2))
    return x + mix*np.convolve(x, ir/moc, mode='full')[:len(x)]

def zapisz(nazwa, x, szczyt_db=-7.0, wyc_ms=12, petla=False):
    # Pętla nie może dostać ani pogłosu, ani wygaszenia na końcu: jedno i drugie
    # robi dziurę w miejscu zapętlenia, którą słychać jako regularny klik.
    if not petla:
        x = poglos(x)
    # wygaszenie na końcu — ucięcie sygnału w locie słychać jako trzask
    if not petla:
        k = int(SR*wyc_ms/1000.0)
        if len(x) > k:
            x[-k:] *= np.linspace(1, 0, k)
    x = x/ (np.max(np.abs(x)) or 1.0) * (10**(szczyt_db/20.0))
    x = x - np.mean(x)                      # zdejmij składową stałą
    sur = os.path.join(KAT, nazwa+'.raw')
    (x*32767).astype('<i2').tofile(sur)
    mp3 = os.path.join(KAT, nazwa+'.mp3')
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
                    '-f','s16le','-ar',str(SR),'-ac','1','-i',sur,
                    '-codec:a','libmp3lame','-b:a','96k', mp3], check=True)
    os.remove(sur)
    return mp3, len(x)/SR

# --------------------------------------------------------------------
ZESTAW = {}

# Przejście stanu agregatu: czysty dzwon, krótki.
ZESTAW['gens'] = dzwon(660, 420, 170, [(1,1.0,1.0),(2,0.34,0.55),(3,0.12,0.35)], 0.9)
# Przejście stanu falownika: oktawę niżej, lekko nieharmoniczny partial —
# brzmi drewniano i nie myli się z agregatem.
ZESTAW['deye'] = dzwon(330, 620, 250, [(1,1.0,1.0),(2,0.26,0.6),(2.76,0.10,0.4)], 0.8)
# Awaria: dwa tony w dół, każdy z parą rozstrojoną o 1,5 Hz — powolne dudnienie
# brzmi poważnie bez podnoszenia głośności.
ZESTAW['fault'] = polacz(
    (0,   ton(233, 420, 300, 0.55) + ton(234.5, 420, 300, 0.45)),
    (190, ton(175, 650, 380, 0.55) + ton(176.5, 650, 380, 0.45)),
)
# Zamknięcie cyklu: jedna miękka nuta z długim ogonem.
ZESTAW['cycle'] = dzwon(440, 700, 320, [(1,1.0,1.0),(2,0.18,0.5)], 0.6)

def zapisz_petle(nazwa, x, szczyt_db=-17.0, sr_out=22050):
    """Pętle idą jako WAV, nie mp3.

    Każdy koder mp3 dokłada ciszę na początku i końcu — tak działa format.
    Przy jednorazowym dźwięku to niewidoczne, przy pętli słychać regularny klik
    w miejscu zapętlenia, co przy silniku psuje całość. WAV jest próbka w próbkę,
    więc szew jest gwarantowany, a nie zależny od tego, jak dana przeglądarka
    odczyta znaczniki gapless. 22,05 kHz wystarcza: treść siedzi poniżej 7 kHz,
    a plik jest o połowę mniejszy.
    """
    x = x - np.mean(x)
    x = x/(np.max(np.abs(x)) or 1.0)*(10**(szczyt_db/20.0))
    # przepróbkowanie liniowe; długość pozostaje całkowitą liczbą cykli
    n_out = int(round(len(x)*sr_out/float(SR)))
    xi = np.interp(np.linspace(0, len(x), n_out, endpoint=False), np.arange(len(x)), x)
    plik = os.path.join(KAT, nazwa+'.wav')
    import wave
    with wave.open(plik,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr_out)
        w.writeframes((xi*32767).astype('<i2').tobytes())
    return plik, n_out/float(sr_out)

# engine-stop zostaje syntezowany: nagrania samego ZATRZYMANIA silnika nie
# znalazłem w domenie publicznej, a w źródle, z którego bierzemy resztę,
# samochód odjeżdża, zamiast gasnąć.
ZESTAW['engine-stop'] = silnik_stop(1600)

if __name__ == '__main__':
    os.makedirs(KAT, exist_ok=True)
    for nazwa, sygnal in ZESTAW.items():
        plik, dl = zapisz(nazwa, sygnal)
        print('  %-13s %5.0f ms  %6d B' % (nazwa, dl*1000, os.path.getsize(plik)))
