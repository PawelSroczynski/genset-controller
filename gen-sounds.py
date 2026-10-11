#!/usr/bin/env python3
"""Generuje zestaw dźwięków symulatora.

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

def zapisz(nazwa, x, szczyt_db=-14.0, wyc_ms=12):
    x = poglos(x)
    # wygaszenie na końcu — ucięcie sygnału w locie słychać jako trzask
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

# Przekaźnik załącza: ostry transjent styku + krótkie uderzenie kotwicy,
# a 11 ms później ciche dosiadanie zwory.
ZESTAW['relay-on'] = polacz(
    (0,  trzask(70, 2.0, 1800, 6500, 1.00, 1)),
    (0,  ton(190, 90, 22, 0.42)),
    (11, trzask(40, 1.6, 1200, 4000, 0.30, 2)),
)
# Przekaźnik odpada: ciszej i niżej — zwolnienie zawsze jest miększe od zwarcia.
ZESTAW['relay-off'] = polacz(
    (0, trzask(55, 2.6, 700, 3200, 0.70, 3)),
    (0, ton(140, 70, 18, 0.30)),
)
# Przejście stanu agregatu: czysty dzwon, krótki.
ZESTAW['gens'] = dzwon(660, 420, 170, [(1,1.0,1.0),(2,0.34,0.55),(3,0.12,0.35)], 0.9)
# Przejście stanu falownika: oktawę niżej, lekko nieharmoniczny partial —
# brzmi drewniano i nie myli się z agregatem.
ZESTAW['deye'] = dzwon(330, 620, 250, [(1,1.0,1.0),(2,0.26,0.6),(2.76,0.10,0.4)], 0.8)
# Potwierdzenie pracy: kwinta czysta w górę.
ZESTAW['running'] = polacz(
    (0,  dzwon(523, 420, 180, [(1,1.0,1.0),(2,0.3,0.5)], 0.75)),
    (95, dzwon(784, 600, 240, [(1,1.0,1.0),(2,0.25,0.5),(3,0.08,0.3)], 0.85)),
)
# Awaria: dwa tony w dół, każdy z parą rozstrojoną o 1,5 Hz — powolne dudnienie
# brzmi poważnie bez podnoszenia głośności.
ZESTAW['fault'] = polacz(
    (0,   ton(233, 420, 300, 0.55) + ton(234.5, 420, 300, 0.45)),
    (190, ton(175, 650, 380, 0.55) + ton(176.5, 650, 380, 0.45)),
)
# Zamknięcie cyklu: jedna miękka nuta z długim ogonem.
ZESTAW['cycle'] = dzwon(440, 700, 320, [(1,1.0,1.0),(2,0.18,0.5)], 0.6)

if __name__ == '__main__':
    os.makedirs(KAT, exist_ok=True)
    for nazwa, sygnal in ZESTAW.items():
        plik, dl = zapisz(nazwa, sygnal)
        print('  %-11s %5.0f ms  %6d B' % (nazwa, dl*1000, os.path.getsize(plik)))
