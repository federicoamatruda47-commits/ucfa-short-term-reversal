# -*- coding: utf-8 -*-
"""
Strategia long/short equity USA basata su short-term reversal
(bande VWAP relative al settore + conferma RSI).

UCFA Finance Society - Universita' Cattolica di Milano

Come si lancia (dal Prompt dei comandi di Windows):
    python strategia.py --demo     -> usa dati simulati, non scarica nulla
    python strategia.py            -> usa dati reali (yfinance), con cache su disco

Sezioni del file:
    0. CONFIGURAZIONE      (tutti i parametri)
    1. DATI                (universo, prezzi, trimestrali, cache, demo)
    2. SEGNALI             (VWAP, z, z_rel, RSI, filtri volume e trimestrali)
    3. BACKTEST            (entrate, uscite, sizing, esposizione, costi, verifica P&L)
    4. METRICHE E CSV      (metriche, in/out-of-sample, sensibilita' costi, CSV)
    5. GRAFICI             (equity vs SPY, drawdown, esposizioni)
"""

import argparse
import io
import pickle
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")   # nasconde gli avvisi gialli di yfinance/pandas (innocui)

# ======================================================================
# 0. CONFIGURAZIONE - qui si cambiano i parametri, nient'altro nel codice
# ======================================================================

# --- Cartelle (relative alla cartella da cui lanci lo script) ---
CARTELLA_OUTPUT = Path("output")   # CSV e grafici finali
CARTELLA_CACHE = Path("cache")     # dati scaricati, per non riscaricarli ogni volta

# --- Date ---
DATA_INIZIO_DOWNLOAD = "2015-01-01"  # il 2015 serve solo per "scaldare" gli indicatori
DATA_FINE_DOWNLOAD = None            # None = fino a oggi
DATA_INIZIO_BACKTEST = "2016-01-01"  # da qui in poi si fanno trade e si misurano i risultati
FINE_IN_SAMPLE = "2021-12-31"        # in-sample: 2016-2021, out-of-sample: dal 2022
BENCHMARK = "SPY"

# --- Segnale VWAP ---
FINESTRA_VWAP = 20          # giorni per VWAP rolling e deviazione standard pesata
FINESTRA_RSI = 14           # periodi dell'RSI di Wilder (calcolato sulla serie z_rel)
SOGLIA_Z_ENTRATA = 1.0      # long se z_rel <= -1, short se z_rel >= +1
SOGLIA_RSI_LONG = 25        # long solo se RSI < 25 (scelto sull'in-sample: riduce il turnover e i costi)
SOGLIA_RSI_SHORT = 75       # short solo se RSI > 75

# --- Filtro volume anomalo ---
FINESTRA_VOL_BREVE = 5      # media del volume sugli ultimi 5 giorni
FINESTRA_VOL_LUNGA = 60     # ... divisa per la media dei 60 giorni precedenti
PERCENTILE_VOLUME_ANOMALO = 0.90  # escluso chi e' nel top 10% dell'universo quel giorno

# --- Filtro sui costi: si entra solo se il guadagno potenziale giustifica il costo ---
MIN_DISTANZA_VWAP = 0.0     # distanza minima del prezzo dal VWAP, in % del prezzo (0.01 = 1%)

# --- Filtro trimestrali ---
GIORNI_DOPO_TRIMESTRALE = 5      # nessuna entrata se trimestrale negli ultimi 5 giorni di borsa
MOLTIPLICATORE_PROXY_VOLUME = 3  # proxy: volume > 3 x media dei 60 giorni precedenti

# --- Uscite ---
SOGLIA_TAKE_PROFIT_Z = 0.0    # take profit quando z_rel rientra entro questo livello (0 = sul VWAP relativo;
                              # 0.5 = esce un po' prima, quando il segnale e' "quasi neutralizzato")
GIORNI_MIN_TAKE_PROFIT = 3   # il take profit vale solo dopo almeno 3 giorni di holding
STOP_LOSS_DEV_STD = 1.5       # stop se z_rel peggiora di 1,5 dev. std. rispetto all'entrata
GIORNI_MAX_HOLDING = 15       # time stop (scelto sull'in-sample)

# --- Sizing ed esposizione ---
RISCHIO_TARGET = 0.08         # peso = 8% / volatilita' annualizzata (scelto sull'in-sample)
FINESTRA_VOLATILITA = 60      # giorni per la volatilita' dei rendimenti log
PESO_MAX_TITOLO = 0.12        # massimo 12% per titolo (scelto sull'in-sample)
GROSS_MAX = 1.50              # gross exposure massima 150% (nessun limite sul net)
GROSS_MAX_SHORT = 0.10        # tetto alla gamba short (10% del capitale); 0 = solo long. Scelto sull'in-sample
GIORNI_ANNO = 252

# --- Costi ---
COSTO_PER_LATO = 0.0010       # 10 bps per lato su ogni variazione di peso
COSTO_PRESTITO_TITOLI = 0.005 # 0,5% annuo sul peso short

# --- Copertura del mercato con lo short sull'ETF SPY ---
VERSIONI = {                      # le due versioni del fondo, entrambe calcolate e confrontate
    "senza_copertura": False,     # long-biased: nessuna copertura del mercato
    "con_copertura": True,        # market-neutral: si vende SPY per annullare il beta del portafoglio
}
FINESTRA_BETA = 60                # giorni per stimare il beta di ogni titolo rispetto a SPY
SOGLIA_RIBILANCIAMENTO = 0.05     # si aggiusta la copertura solo se cambia di oltre il 5% del capitale
COSTO_COPERTURA_PER_LATO = 0.0002 # 2 bps per lato su SPY (ipotesi: molto piu' liquido delle azioni singole)
COSTO_PRESTITO_COPERTURA = 0.0025 # 0,25% annuo sul valore di SPY venduto allo scoperto

# --- Analisi di sensibilita' ai costi e formato dei CSV ---
SENSIBILITA_COSTI_BPS = [10, 5, 3, 2]  # costo per lato sulle azioni da provare (10 = caso base)
CSV_SEP = ";"                          # separatore: ";" si apre bene in Excel italiano
CSV_DECIMALE = ","                     # virgola decimale (metti "." e "," se usi Python/Excel inglese)

# --- Le 4 varianti, ognuna aggiunge un miglioramento alla precedente ---
VARIANTI = {
    "1_Generica": dict(usa_settore=False, filtro_volume=False, filtro_trimestrali=False),
    "2_Settore": dict(usa_settore=True, filtro_volume=False, filtro_trimestrali=False),
    "3_Volume": dict(usa_settore=True, filtro_volume=True, filtro_trimestrali=False),
    "4_Completa": dict(usa_settore=True, filtro_volume=True, filtro_trimestrali=True),
}

# --- Download (parametri tecnici) ---
DIMENSIONE_BLOCCO_DOWNLOAD = 100  # quanti ticker scaricare per volta
THREAD_PARALLELI = 8              # richieste parallele per le trimestrali

# --- Modalita' demo ---
DEMO_N_TITOLI = 80
DEMO_SEED = 42


# ======================================================================
# 1. DATI
# ======================================================================
# Tutte le funzioni di questa sezione restituiscono i dati in forma "larga":
# una tabella con le date sulle righe e i ticker sulle colonne.
# Il risultato finale e' un dizionario con queste chiavi:
#   "open", "high", "low", "close", "volume" -> tabelle date x ticker
#   "spy"        -> DataFrame con la colonna "open" e "close" di SPY
#   "settori"    -> Series: ticker -> settore GICS
#   "trimestrali"-> dict: ticker -> lista di date di trimestrale (o None se non disponibili)


def _salva_cache(nome, oggetto):
    """Salva un oggetto Python su disco (cartella cache)."""
    CARTELLA_CACHE.mkdir(parents=True, exist_ok=True)
    with open(CARTELLA_CACHE / nome, "wb") as f:
        pickle.dump(oggetto, f)


def _leggi_cache(nome):
    """Legge un oggetto dalla cache. Restituisce None se non esiste."""
    percorso = CARTELLA_CACHE / nome
    if percorso.exists():
        with open(percorso, "rb") as f:
            return pickle.load(f)
    return None


def scarica_universo():
    """Scarica da Wikipedia i costituenti attuali dell'S&P 500 con il settore GICS."""
    import requests

    cache = _leggi_cache("universo.pkl")
    if cache is not None:
        print("Universo: letto dalla cache")
        return cache

    print("Universo: download da Wikipedia...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    # Wikipedia blocca le richieste anonime: ci presentiamo con uno User-Agent
    risposta = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (UCFA backtest)"}, timeout=30)
    risposta.raise_for_status()
    tabella = pd.read_html(io.StringIO(risposta.text))[0]

    # yfinance vuole il trattino al posto del punto (BRK.B -> BRK-B)
    tickers = tabella["Symbol"].astype(str).str.replace(".", "-", regex=False)
    settori = pd.Series(tabella["GICS Sector"].values, index=tickers.values, name="settore")
    settori = settori[~settori.index.duplicated()]

    _salva_cache("universo.pkl", settori)
    return settori


def scarica_prezzi(tickers):
    """Scarica OHLCV giornalieri aggiustati (dividendi e split) per tutti i ticker."""
    import yfinance as yf

    cache = _leggi_cache("prezzi.pkl")
    if cache is not None:
        print("Prezzi: letti dalla cache")
        return cache

    print(f"Prezzi: download di {len(tickers)} titoli (puo' richiedere qualche minuto)...")
    pezzi = []
    tickers = list(tickers)
    for i in range(0, len(tickers), DIMENSIONE_BLOCCO_DOWNLOAD):
        blocco = tickers[i:i + DIMENSIONE_BLOCCO_DOWNLOAD]
        dati = yf.download(
            blocco,
            start=DATA_INIZIO_DOWNLOAD,
            end=DATA_FINE_DOWNLOAD,
            auto_adjust=True,      # prezzi gia' aggiustati per dividendi e split
            progress=False,
            threads=True,
        )
        pezzi.append(dati)
        print(f"  scaricati {min(i + DIMENSIONE_BLOCCO_DOWNLOAD, len(tickers))}/{len(tickers)}")

    grande = pd.concat(pezzi, axis=1)
    risultato = {
        "open": grande["Open"], "high": grande["High"], "low": grande["Low"],
        "close": grande["Close"], "volume": grande["Volume"],
    }
    # eliminiamo i ticker senza nessun dato
    validi = risultato["close"].columns[risultato["close"].notna().any()]
    risultato = {k: v[validi].sort_index() for k, v in risultato.items()}

    _salva_cache("prezzi.pkl", risultato)
    return risultato


def scarica_benchmark():
    """Scarica SPY (apertura e chiusura) per il confronto."""
    import yfinance as yf

    cache = _leggi_cache("spy.pkl")
    if cache is not None:
        print("Benchmark: letto dalla cache")
        return cache

    print("Benchmark: download SPY...")
    dati = yf.download(BENCHMARK, start=DATA_INIZIO_DOWNLOAD, end=DATA_FINE_DOWNLOAD,
                       auto_adjust=True, progress=False)
    # con versioni recenti di yfinance le colonne possono essere a due livelli
    if isinstance(dati.columns, pd.MultiIndex):
        dati.columns = dati.columns.get_level_values(0)
    spy = pd.DataFrame({"open": dati["Open"], "close": dati["Close"]}).sort_index()

    _salva_cache("spy.pkl", spy)
    return spy


def scarica_trimestrali(tickers):
    """Scarica le date delle trimestrali. Per i ticker senza dati il valore e' None
    (in quel caso il segnale usera' il proxy sul volume)."""
    import yfinance as yf

    cache = _leggi_cache("trimestrali.pkl")
    if cache is not None:
        print("Trimestrali: lette dalla cache")
        return cache

    print("Trimestrali: download date (puo' richiedere alcuni minuti)...")

    def uno(t):
        try:
            date = yf.Ticker(t).get_earnings_dates(limit=60)
            if date is None or len(date) == 0:
                return t, None
            idx = pd.DatetimeIndex(date.index)
            if idx.tz is not None:
                idx = idx.tz_localize(None)
            return t, sorted(idx.normalize().unique())
        except Exception:
            return t, None

    with ThreadPoolExecutor(max_workers=THREAD_PARALLELI) as pool:
        risultato = dict(pool.map(uno, tickers))

    _salva_cache("trimestrali.pkl", risultato)
    return risultato


def genera_dati_demo():
    """Dati simulati (random walk) per provare il codice senza internet."""
    print("MODALITA' DEMO: dati simulati, nessun download.")
    rng = np.random.default_rng(DEMO_SEED)
    date = pd.bdate_range(DATA_INIZIO_DOWNLOAD, "2025-12-31")
    n = DEMO_N_TITOLI
    tickers = [f"TIT{i:03d}" for i in range(n)]
    nomi_settori = ["Information Technology", "Health Care", "Financials", "Industrials",
                    "Consumer Discretionary", "Consumer Staples", "Energy", "Utilities",
                    "Materials", "Real Estate", "Communication Services"]
    settori = pd.Series([nomi_settori[i % len(nomi_settori)] for i in range(n)],
                        index=tickers, name="settore")

    # rendimenti = componente di mercato + componente di settore + componente del titolo
    mercato = rng.normal(0.0003, 0.010, len(date))
    comp_settore = {s: rng.normal(0, 0.006, len(date)) for s in nomi_settori}
    vol_titolo = rng.uniform(0.008, 0.02, n)
    rend = np.zeros((len(date), n))
    for j, t in enumerate(tickers):
        rend[:, j] = mercato + comp_settore[settori[t]] + rng.normal(0, vol_titolo[j], len(date))

    close = pd.DataFrame(100 * np.exp(np.cumsum(rend, axis=0)), index=date, columns=tickers)
    gap = rng.normal(0, 0.004, (len(date), n))              # differenza chiusura->apertura
    open_ = close.shift(1).fillna(close.iloc[0]) * np.exp(gap)
    ampiezza = np.abs(rng.normal(0, 0.006, (len(date), n)))
    high = np.maximum(open_, close) * (1 + ampiezza)
    low = np.minimum(open_, close) * (1 - ampiezza)
    volume = pd.DataFrame(rng.lognormal(14, 0.4, (len(date), n)), index=date, columns=tickers)

    # trimestrali simulate: una ogni ~63 giorni, con volume maggiorato quel giorno
    trimestrali = {}
    for j, t in enumerate(tickers):
        pos = np.arange(rng.integers(5, 60), len(date), 63)
        trimestrali[t] = [date[p] for p in pos]
        volume.iloc[pos, j] *= 4
        if j % 10 == 0:
            trimestrali[t] = None     # alcuni titoli "senza date" per provare il proxy

    spy_close = pd.Series(100 * np.exp(np.cumsum(mercato)), index=date)
    spy = pd.DataFrame({"open": spy_close.shift(1).fillna(spy_close.iloc[0]),
                        "close": spy_close})

    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume,
            "spy": spy, "settori": settori, "trimestrali": trimestrali}


def carica_dati(demo=False):
    """Punto di ingresso della sezione dati: restituisce il dizionario completo."""
    if demo:
        return genera_dati_demo()

    settori = scarica_universo()
    prezzi = scarica_prezzi(settori.index)
    # teniamo solo i titoli con prezzi effettivamente scaricati
    settori = settori[settori.index.isin(prezzi["close"].columns)]
    tickers = list(settori.index)

    dati = dict(prezzi)
    dati["spy"] = scarica_benchmark()
    dati["settori"] = settori
    dati["trimestrali"] = scarica_trimestrali(tickers)
    return dati


def riepilogo_dati(dati):
    """Stampa un controllo rapido sui dati caricati."""
    c = dati["close"]
    print("\n--- Riepilogo dati ---")
    print(f"Titoli: {c.shape[1]}  |  giorni: {c.shape[0]}  |  dal {c.index[0].date()} al {c.index[-1].date()}")
    print(f"Settori: {dati['settori'].nunique()}")
    con_date = sum(1 for v in dati["trimestrali"].values() if v)
    print(f"Titoli con date trimestrali: {con_date}/{len(dati['trimestrali'])}")
    print(f"Celle di prezzo mancanti: {c.isna().mean().mean():.1%}")


# ======================================================================
# 2. SEGNALI
# ======================================================================
# Tutto e' calcolato con la chiusura del giorno d (nessun dato futuro):
# il trade, nel backtest, avverra' all'apertura di d+1.
# Tutte le tabelle sono "date x ticker".

def calcola_vwap_z(dati):
    """VWAP rolling, deviazione standard pesata per volume e z = distanza dal VWAP in sigma."""
    n = FINESTRA_VWAP
    tp = (dati["high"] + dati["low"] + dati["close"]) / 3      # typical price
    vol = dati["volume"]

    somma_vol = vol.rolling(n, min_periods=n).sum()
    vwap = (tp * vol).rolling(n, min_periods=n).sum() / somma_vol
    # varianza pesata = media pesata di TP^2 meno VWAP^2 (puo' uscire leggermente
    # negativa per errori di arrotondamento: la portiamo a zero)
    varianza = (vol * tp ** 2).rolling(n, min_periods=n).sum() / somma_vol - vwap ** 2
    sigma = np.sqrt(varianza.clip(lower=0))

    z = (dati["close"] - vwap) / sigma.replace(0, np.nan)     # sigma = 0 -> nessun segnale
    return z, vwap


def z_relativo_al_settore(z, settori):
    """z_rel = z del titolo meno la mediana di z del suo settore, lo stesso giorno."""
    mediane = pd.DataFrame(index=z.index, columns=z.columns, dtype=float)
    for settore in settori.unique():
        colonne = settori.index[settori == settore].intersection(z.columns)
        if len(colonne) == 0:
            continue
        mediana_giorno = z[colonne].median(axis=1)             # una mediana per giorno
        mediane[colonne] = np.tile(mediana_giorno.values[:, None], (1, len(colonne)))
    return z - mediane


def rsi_wilder(serie, periodi=None):
    """RSI di Wilder: media mobile esponenziale con alpha = 1/periodi (calcolo di Wilder).
    Funziona su una tabella intera, colonna per colonna. Qui la 'serie' e' z o z_rel,
    non il prezzo."""
    p = periodi or FINESTRA_RSI
    variazione = serie.diff()
    guadagni = variazione.clip(lower=0)
    perdite = (-variazione).clip(lower=0)
    media_g = guadagni.ewm(alpha=1 / p, adjust=False, min_periods=p).mean()
    media_p = perdite.ewm(alpha=1 / p, adjust=False, min_periods=p).mean()
    rs = media_g / media_p
    rsi = 100 - 100 / (1 + rs)
    # se non ci sono mai state perdite l'RSI vale 100 (e 0 se non ci sono guadagni)
    rsi = rsi.where(media_p != 0, 100.0)
    rsi = rsi.where(~((media_g == 0) & (media_p == 0)), 50.0)
    return rsi.where(media_g.notna() & media_p.notna())


def volume_relativo(volume):
    """Media volume ultimi 5 giorni / media dei 60 giorni precedenti a quei 5."""
    breve = volume.rolling(FINESTRA_VOL_BREVE, min_periods=FINESTRA_VOL_BREVE).mean()
    lunga = volume.shift(FINESTRA_VOL_BREVE).rolling(
        FINESTRA_VOL_LUNGA, min_periods=FINESTRA_VOL_LUNGA).mean()
    return breve / lunga


def flag_volume_anomalo(vol_rel):
    """True se il volume relativo del titolo e' nel top 10% dell'universo quel giorno."""
    percentile = vol_rel.rank(axis=1, pct=True)   # 1.0 = il piu' alto del giorno
    return percentile > PERCENTILE_VOLUME_ANOMALO


def flag_trimestrale_recente(dati):
    """True se c'e' stata una trimestrale negli ultimi 5 giorni di borsa (giorno d compreso).
    Si usano le date vere di yfinance dove coprono il periodo; altrove il proxy:
    un giorno con volume > 3 x la media dei 60 giorni precedenti."""
    volume = dati["volume"]
    date = volume.index

    # proxy: picco di volume rispetto ai 60 giorni precedenti (il giorno stesso escluso)
    media_prec = volume.shift(1).rolling(FINESTRA_VOL_LUNGA, min_periods=FINESTRA_VOL_LUNGA).mean()
    evento_proxy = volume > MOLTIPLICATORE_PROXY_VOLUME * media_prec

    evento_vero = pd.DataFrame(False, index=date, columns=volume.columns)
    coperto = pd.DataFrame(False, index=date, columns=volume.columns)  # dove le date vere valgono
    for t in volume.columns:
        elenco = dati["trimestrali"].get(t)
        if not elenco:
            continue                                 # nessuna data: si usa solo il proxy
        elenco = pd.DatetimeIndex(elenco)
        # ogni data viene attaccata al primo giorno di borsa uguale o successivo
        pos = date.searchsorted(elenco)
        pos = pos[pos < len(date)]
        evento_vero.iloc[pos, evento_vero.columns.get_loc(t)] = True
        # le date di yfinance coprono solo gli ultimi anni: prima della prima data
        # nota (meno ~70 giorni, un trimestre) la copertura e' considerata assente
        inizio_copertura = elenco.min() - pd.Timedelta(days=70)
        coperto.loc[date >= inizio_copertura, t] = True

    evento = evento_vero.where(coperto, evento_proxy).fillna(False).astype(bool)
    # "negli ultimi 5 giorni": finestra mobile che include il giorno d
    recente = evento.astype(int).rolling(GIORNI_DOPO_TRIMESTRALE, min_periods=1).max() > 0
    return recente


def volatilita_annua(close):
    """Deviazione standard a 60 giorni dei rendimenti log, annualizzata."""
    rend_log = np.log(close / close.shift(1))
    return rend_log.rolling(FINESTRA_VOLATILITA, min_periods=FINESTRA_VOLATILITA).std() * np.sqrt(GIORNI_ANNO)


def beta_rolling(dati):
    """Beta di ogni titolo rispetto a SPY sugli ultimi 60 giorni (rendimenti chiusura-chiusura).
    Dove non e' calcolabile si usa 1 (il titolo si muove come il mercato)."""
    rend = dati["close"].pct_change()
    rend_spy = dati["spy"]["close"].reindex(dati["close"].index).pct_change()
    cov = rend.rolling(FINESTRA_BETA, min_periods=FINESTRA_BETA).cov(rend_spy)
    var = rend_spy.rolling(FINESTRA_BETA, min_periods=FINESTRA_BETA).var()
    return cov.div(var, axis=0).clip(-1, 3).fillna(1.0)


def calcola_segnali(dati):
    """Calcola tutti i segnali e li restituisce in un dizionario di tabelle."""
    print("Segnali: calcolo in corso...")
    z, vwap = calcola_vwap_z(dati)
    z_rel = z_relativo_al_settore(z, dati["settori"])
    vol_rel = volume_relativo(dati["volume"])
    return {
        "z": z,                                   # variante 1 (generica)
        "z_rel": z_rel,                           # varianti 2-4
        "rsi_z": rsi_wilder(z),                   # RSI su z (variante 1)
        "rsi_z_rel": rsi_wilder(z_rel),           # RSI su z_rel (varianti 2-4)
        "vol_rel": vol_rel,
        "vol_anomalo": flag_volume_anomalo(vol_rel),
        "trim_recente": flag_trimestrale_recente(dati),
        "volatilita": volatilita_annua(dati["close"]),
        "beta": beta_rolling(dati),
        # distanza in % del prezzo dal VWAP: e' il guadagno potenziale se il prezzo rientra
        "dist_vwap": ((dati["close"] - vwap) / dati["close"]).abs(),
    }


def riepilogo_segnali(s):
    """Controllo rapido: quante volte scattano i segnali di entrata (prima dei filtri)."""
    inizio = pd.Timestamp(DATA_INIZIO_BACKTEST)
    def conta(z, rsi):
        long_ = (z <= -SOGLIA_Z_ENTRATA) & (rsi < SOGLIA_RSI_LONG)
        short = (z >= SOGLIA_Z_ENTRATA) & (rsi > SOGLIA_RSI_SHORT)
        return long_.loc[inizio:].sum().sum(), short.loc[inizio:].sum().sum(), long_, short
    print("\n--- Riepilogo segnali (dal inizio backtest, titolo-giorni) ---")
    for nome, z, rsi in [("z generico", s["z"], s["rsi_z"]), ("z_rel settore", s["z_rel"], s["rsi_z_rel"])]:
        nl, ns, long_, short = conta(z, rsi)
        print(f"{nome:14s}: candidati long {nl}, short {ns}")
    _, _, long_, short = conta(s["z_rel"], s["rsi_z_rel"])
    cand = (long_ | short).loc[inizio:]
    print(f"Dei candidati z_rel: escluso da volume anomalo {(cand & s['vol_anomalo'].loc[inizio:]).sum().sum()}, "
          f"da trimestrale recente {(cand & s['trim_recente'].loc[inizio:]).sum().sum()}")
    print(f"Quota di titolo-giorni con trimestrale recente: {s['trim_recente'].loc[inizio:].mean().mean():.1%}")


# ======================================================================
# 3. BACKTEST
# ======================================================================
# Cronologia di ogni giorno t (il segnale e' calcolato alla chiusura di d = t-1):
#   1. all'apertura di t escono le posizioni per cui alla chiusura di d e' scattata un'uscita
#   2. all'apertura di t entrano i nuovi candidati scelti alla chiusura di d
#   3. rendimento del giorno t:
#        - posizioni che escono:  solo overnight (chiusura d -> apertura t)
#        - posizioni gia' aperte: overnight + intraday (apertura t -> chiusura t)
#        - posizioni nuove:       solo intraday
#   4. costi: 10 bps sul peso di ogni entrata/uscita + prestito titoli sugli short a fine giornata
# Il rendimento di una posizione e' lato * peso * rendimento, con peso fisso dall'entrata all'uscita.

def _rendimenti_overnight_intraday(dati):
    """Due tabelle (come array): overnight (chiusura ieri -> apertura oggi) e intraday
    (apertura -> chiusura oggi). I valori mancanti diventano 0."""
    chiusura = dati["close"].values
    apertura = dati["open"].values
    overnight = np.zeros_like(chiusura)
    overnight[1:] = apertura[1:] / chiusura[:-1] - 1
    intraday = chiusura / apertura - 1
    pulisci = lambda a: np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
    return pulisci(overnight), pulisci(intraday)


def _rendimenti_spy(dati):
    """Overnight e intraday di SPY, allineati alle date dei titoli (mancanti = 0)."""
    spy = dati["spy"].reindex(dati["close"].index)
    on = np.zeros(len(spy))
    on[1:] = spy["open"].values[1:] / spy["close"].values[:-1] - 1
    intra = spy["close"].values / spy["open"].values - 1
    return np.nan_to_num(on), np.nan_to_num(intra)


def _ricostruisci_da_trade(trades, overnight, intraday):
    """Ricostruisce rendimenti e costi giornalieri SOLO dal log dei trade.
    Serve sia per riempire il P&L di ogni trade sia per la verifica finale."""
    T = overnight.shape[0]
    lordo, costo_trading, costo_prestito, turnover = (np.zeros(T) for _ in range(4))
    pnl_trade = np.zeros(len(trades))
    costi_trade = np.zeros(len(trades))
    for k, tr in enumerate(trades.itertuples()):
        e = int(tr.idx_entrata)
        aperta = pd.isna(tr.idx_uscita)
        x = T - 1 if aperta else int(tr.idx_uscita)   # ultimo giorno con rendimento
        j, s, w = tr.col, tr.segno, tr.peso
        giorni = overnight[e:x + 1, j] + intraday[e:x + 1, j]
        giorni[0] = intraday[e, j]                     # primo giorno: solo intraday
        if not aperta:
            giorni[-1] = overnight[x, j]               # giorno di uscita: solo overnight
        contributi = s * w * giorni
        lordo[e:x + 1] += contributi
        pnl_trade[k] = contributi.sum()

        costo_in = w * COSTO_PER_LATO
        costo_trading[e] += costo_in; turnover[e] += w
        costi_trade[k] += costo_in
        if not aperta:
            costo_trading[x] += costo_in; turnover[x] += w
            costi_trade[k] += costo_in
        if s == -1:                                    # prestito: dal giorno d'entrata a quello prima dell'uscita
            ultimo = T - 1 if aperta else x - 1
            costo_prestito[e:ultimo + 1] += w * COSTO_PRESTITO_TITOLI / GIORNI_ANNO
            costi_trade[k] += w * COSTO_PRESTITO_TITOLI / GIORNI_ANNO * (ultimo - e + 1)
    return lordo, costo_trading, costo_prestito, turnover, pnl_trade, costi_trade


def esegui_backtest(dati, segnali, usa_settore, filtro_volume, filtro_trimestrali, copertura=False):
    """Backtest di una variante. Restituisce rendimenti giornalieri e log dei trade.
    copertura=True aggiunge la vendita di SPY per annullare il beta del portafoglio."""
    date = dati["close"].index
    colonne = dati["close"].columns
    T, N = dati["close"].shape
    apertura = dati["open"].values
    z = segnali["z_rel" if usa_settore else "z"].values
    rsi = segnali["rsi_z_rel" if usa_settore else "rsi_z"].values
    vol_anomalo = segnali["vol_anomalo"].values
    trimestrale = segnali["trim_recente"].values
    volat = segnali["volatilita"].values
    beta = segnali["beta"].values
    dist_vwap = segnali["dist_vwap"].values
    overnight, intraday = _rendimenti_overnight_intraday(dati)
    on_spy, intra_spy = _rendimenti_spy(dati)
    h = 0.0                                  # copertura: valore di SPY in portafoglio (negativo = short)

    inizio = max(int(date.searchsorted(pd.Timestamp(DATA_INIZIO_BACKTEST))), 1)

    # stato delle posizioni aperte (un elemento per ticker)
    lato = np.zeros(N)                       # +1 long, -1 short, 0 nessuna posizione
    peso = np.zeros(N)
    idx_ent = np.zeros(N, dtype=int)         # indice del giorno d'entrata
    z_ent = np.zeros(N)                      # z (o z_rel) del giorno del segnale
    id_trade = np.full(N, -1)                # posizione del trade nella lista log
    trades = []
    righe = []

    for t in range(inizio, T):
        d = t - 1
        zd = z[d]

        # ---- 1. uscite decise alla chiusura di d ----
        in_pos = lato != 0
        giorni_hold = d - idx_ent + 1
        stop = in_pos & (((lato == 1) & (zd <= z_ent - STOP_LOSS_DEV_STD)) |
                         ((lato == -1) & (zd >= z_ent + STOP_LOSS_DEV_STD)))
        tp = in_pos & (giorni_hold >= GIORNI_MIN_TAKE_PROFIT) & (
            ((lato == 1) & (zd >= -SOGLIA_TAKE_PROFIT_Z)) | ((lato == -1) & (zd <= SOGLIA_TAKE_PROFIT_Z)))
        tempo = in_pos & (giorni_hold >= GIORNI_MAX_HOLDING)
        # se ne scattano piu' d'una vale la prima: stop, poi take profit, poi time stop
        motivo = np.where(stop, "stop_loss", np.where(tp, "take_profit", np.where(tempo, "time_stop", "")))
        esce = motivo != ""

        # rendimento del giorno per le posizioni gia' aperte
        pnl = (lato * peso * overnight[t]).sum() + (lato * peso * intraday[t])[~esce].sum()
        peso_uscito = peso[esce].sum()
        for j in np.where(esce)[0]:
            tr = trades[id_trade[j]]
            tr["idx_uscita"] = t
            tr["motivo_uscita"] = motivo[j]
            lato[j] = 0; peso[j] = 0; id_trade[j] = -1

        # ---- 2. entrate decise alla chiusura di d ----
        # chi era in portafoglio (anche se esce oggi) non puo' entrare: niente rientro nel giorno di chiusura
        libero = (~in_pos) & np.isfinite(apertura[t]) & np.isfinite(volat[d]) & (volat[d] > 0)
        cand_long = libero & (zd <= -SOGLIA_Z_ENTRATA) & (rsi[d] < SOGLIA_RSI_LONG)
        cand_short = libero & (zd >= SOGLIA_Z_ENTRATA) & (rsi[d] > SOGLIA_RSI_SHORT)
        candidati = cand_long | cand_short
        if MIN_DISTANZA_VWAP > 0:
            candidati &= dist_vwap[d] >= MIN_DISTANZA_VWAP        # guadagno potenziale > costi
        if filtro_volume:
            candidati &= ~vol_anomalo[d]
        if filtro_trimestrali:
            candidati &= ~trimestrale[d]

        peso_entrato = 0.0
        gross = peso.sum()
        gross_short = peso[lato == -1].sum()
        idx = np.where(candidati)[0]
        idx = idx[np.argsort(-np.abs(zd[idx]), kind="stable")]       # prima |z| piu' alto
        for j in idx:
            w = min(RISCHIO_TARGET / volat[d, j], PESO_MAX_TITOLO)
            if gross + w > GROSS_MAX + 1e-12:
                continue                                              # sforerebbe il 150%: non si apre
            segno = 1.0 if cand_long[j] else -1.0
            if segno == -1.0 and gross_short + w > GROSS_MAX_SHORT + 1e-12:
                continue                                              # tetto sulla gamba short
            if segno == -1.0:
                gross_short += w
            lato[j], peso[j], idx_ent[j], z_ent[j] = segno, w, t, zd[j]
            id_trade[j] = len(trades)
            trades.append(dict(
                ticker=colonne[j], col=j, lato="long" if segno == 1 else "short", segno=segno,
                data_segnale=date[d], data_entrata=date[t], idx_entrata=t,
                prezzo_entrata=apertura[t, j], peso=w, z_entrata=zd[j], rsi_entrata=rsi[d, j],
                idx_uscita=np.nan, motivo_uscita="aperta_a_fine"))
            gross += w
            peso_entrato += w
            pnl += segno * w * intraday[t, j]                         # le nuove prendono solo l'intraday

        # ---- 3. copertura con SPY (decisa con i beta di d, eseguita all'apertura di t) ----
        net_beta = (lato * peso * beta[d]).sum()          # esposizione al mercato del portafoglio
        h_prima = h
        if copertura and abs(-net_beta - h) > SOGLIA_RIBILANCIAMENTO:
            h = -net_beta                                 # si vende SPY per annullare il beta
        # come per i titoli: il vecchio importo prende l'overnight, il nuovo l'intraday
        ret_copertura = h_prima * on_spy[t] + h * intra_spy[t]
        costo_copertura = (abs(h - h_prima) * COSTO_COPERTURA_PER_LATO
                           + max(-h, 0.0) * COSTO_PRESTITO_COPERTURA / GIORNI_ANNO)

        # ---- 4. costi e statistiche del giorno ----
        costo_trading = (peso_uscito + peso_entrato) * COSTO_PER_LATO
        costo_prestito = peso[lato == -1].sum() * COSTO_PRESTITO_TITOLI / GIORNI_ANNO
        netto = pnl + ret_copertura - costo_trading - costo_prestito - costo_copertura
        righe.append((date[t], pnl, costo_trading, costo_prestito, netto,
                      peso.sum(), (lato * peso).sum(), int((lato == 1).sum()), int((lato == -1).sum()),
                      peso_uscito + peso_entrato, ret_copertura, costo_copertura, h, net_beta))

    giornaliero = pd.DataFrame(righe, columns=[
        "data", "ret_lordo", "costo_trading", "costo_prestito", "ret_netto", "gross", "net",
        "n_long", "n_short", "turnover", "ret_copertura", "costo_copertura", "copertura",
        "beta_portafoglio"]).set_index("data")

    # log dei trade con P&L e costi ricostruiti dal log stesso
    log = pd.DataFrame(trades)
    if len(log):
        _, _, _, _, pnl_trade, costi_trade = _ricostruisci_da_trade(log, overnight, intraday)
        log["pnl_lordo"] = pnl_trade                    # contributo al rendimento del portafoglio
        log["costi"] = costi_trade
        log["pnl_netto"] = pnl_trade - costi_trade
        log["data_uscita"] = [date[int(i)] if not pd.isna(i) else pd.NaT for i in log["idx_uscita"]]
        fine = np.where(log["idx_uscita"].isna(), T - 1, log["idx_uscita"]).astype(int)
        log["giorni_holding"] = fine - log["idx_entrata"]
        prezzo_fine = np.where(log["idx_uscita"].isna(),
                               dati["close"].values[T - 1, log["col"]],
                               apertura[fine, log["col"]])
        log["rend_titolo"] = log["segno"] * (prezzo_fine / log["prezzo_entrata"] - 1)
    return {"giornaliero": giornaliero, "trades": log}


def verifica_pnl(dati, risultato, nome=""):
    """Controllo di coerenza: ricostruisce il P&L giornaliero dal solo log dei trade
    e lo confronta con quello del motore di backtest."""
    overnight, intraday = _rendimenti_overnight_intraday(dati)
    g, tr, pr, turn, _, _ = _ricostruisci_da_trade(risultato["trades"], overnight, intraday)
    quotidiano = risultato["giornaliero"]
    pos = dati["close"].index.get_indexer(quotidiano.index)
    diff = max(np.abs(g[pos] - quotidiano["ret_lordo"].values).max(),
               np.abs(tr[pos] - quotidiano["costo_trading"].values).max(),
               np.abs(pr[pos] - quotidiano["costo_prestito"].values).max(),
               np.abs(turn[pos] - quotidiano["turnover"].values).max())
    assert diff < 1e-10, f"[{nome}] P&L del motore e del log NON coincidono (diff max {diff:.2e})"

    # copertura: rendimento e costi ricalcolati dalla sola serie dei valori di SPY in portafoglio
    on_spy, intra_spy = _rendimenti_spy(dati)
    h = quotidiano["copertura"].values
    h_prima = np.concatenate([[0.0], h[:-1]])
    ret_h = h_prima * on_spy[pos] + h * intra_spy[pos]
    costo_h = np.abs(h - h_prima) * COSTO_COPERTURA_PER_LATO + np.maximum(-h, 0) * COSTO_PRESTITO_COPERTURA / GIORNI_ANNO
    diff_h = max(np.abs(ret_h - quotidiano["ret_copertura"].values).max(),
                 np.abs(costo_h - quotidiano["costo_copertura"].values).max())
    # il netto totale deve essere la somma di tutte le componenti
    netto = (quotidiano["ret_lordo"] + quotidiano["ret_copertura"] - quotidiano["costo_trading"]
             - quotidiano["costo_prestito"] - quotidiano["costo_copertura"])
    diff_n = np.abs(netto - quotidiano["ret_netto"]).max()
    assert max(diff_h, diff_n) < 1e-10, f"[{nome}] copertura/netto non coerenti ({diff_h:.2e}, {diff_n:.2e})"
    print(f"Verifica P&L {nome}: OK (titoli {diff:.1e}, copertura {diff_h:.1e}, netto {diff_n:.1e})")


def esegui_tutte_le_varianti(dati, segnali):
    """Lancia le 4 varianti nelle 2 versioni (senza/con copertura), verifica il P&L di ciascuna.
    Restituisce risultati[versione][variante]."""
    risultati = {}
    for versione, copertura in VERSIONI.items():
        risultati[versione] = {}
        for nome, opzioni in VARIANTI.items():
            r = esegui_backtest(dati, segnali, copertura=copertura, **opzioni)
            verifica_pnl(dati, r, f"{versione}/{nome}")
            risultati[versione][nome] = r
            g, tr = r["giornaliero"], r["trades"]
            print(f"  {versione}/{nome}: {len(tr)} trade, gross medio {g['gross'].mean():.0%}")
    return risultati


# ======================================================================
# 4. METRICHE E CSV
# ======================================================================
# Tutte le metriche sono al netto dei costi (tasso privo di rischio = 0).

def periodi_di_analisi(indice):
    """Divide le date in totale / in-sample (fino a FINE_IN_SAMPLE) / out-of-sample (dopo)."""
    fine = pd.Timestamp(FINE_IN_SAMPLE)
    return {"totale": indice == indice,
            "in_sample": indice <= fine,
            "out_of_sample": indice > fine}


def calcola_metriche(g, rend_spy):
    """Metriche di performance di una serie giornaliera (tabella 'giornaliero' o un suo pezzo)."""
    r = g["ret_netto"]
    n = len(r)
    if n < 20:
        return {}
    anni = n / GIORNI_ANNO
    cagr = (1 + r).prod() ** (1 / anni) - 1
    vol = r.std() * np.sqrt(GIORNI_ANNO)
    sharpe = r.mean() * GIORNI_ANNO / vol if vol > 0 else np.nan
    # Sortino: si divide per la volatilita' dei soli rendimenti negativi
    downside = np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(GIORNI_ANNO)
    sortino = r.mean() * GIORNI_ANNO / downside if downside > 0 else np.nan
    equity = np.concatenate([[1.0], (1 + r).cumprod().values])
    max_dd = (equity / np.maximum.accumulate(equity) - 1).min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan

    m = rend_spy.reindex(r.index).fillna(0.0)
    beta = np.cov(r, m)[0, 1] / m.var() if m.var() > 0 else np.nan
    return {
        "cagr": cagr, "volatilita": vol, "sharpe": sharpe, "sortino": sortino,
        "max_drawdown": max_dd, "calmar": calmar,
        "rendimento_lordo_annuo": (g["ret_lordo"] + g["ret_copertura"]).mean() * GIORNI_ANNO,
        "costi_annui": (g["costo_trading"] + g["costo_prestito"] + g["costo_copertura"]).mean() * GIORNI_ANNO,
        "turnover_annuo": g["turnover"].mean() * GIORNI_ANNO,
        "gross_medio": g["gross"].mean(),
        "net_medio_titoli": g["net"].mean(),
        "net_medio_con_copertura": (g["net"] + g["copertura"]).mean(),
        "n_long_medio": g["n_long"].mean(), "n_short_medio": g["n_short"].mean(),
        "beta_spy": beta, "correlazione_spy": r.corr(m),
    }


def metriche_spy(rend_spy, indice):
    """Le stesse metriche principali per SPY (buy & hold), per il confronto."""
    r = rend_spy.reindex(indice).fillna(0.0)
    finto = pd.DataFrame({"ret_netto": r, "ret_lordo": r, "ret_copertura": 0.0, "costo_trading": 0.0,
                          "costo_prestito": 0.0, "costo_copertura": 0.0, "turnover": 0.0, "gross": 1.0,
                          "net": 1.0, "copertura": 0.0, "n_long": 1, "n_short": 0})
    return finto


def statistiche_trade(trades):
    """Statistiche sui trade, per gruppo: tutti, long, short e per motivo d'uscita.
    Hit rate e rendimento medio sono del titolo (lato incluso), prima dei costi."""
    righe = []
    gruppi = [("tutti", trades)]
    for lato in ["long", "short"]:
        gruppi.append((f"lato_{lato}", trades[trades["lato"] == lato]))
    for motivo in ["take_profit", "stop_loss", "time_stop", "aperta_a_fine"]:
        gruppi.append((f"uscita_{motivo}", trades[trades["motivo_uscita"] == motivo]))
    for nome, t in gruppi:
        righe.append({
            "gruppo": nome, "n_trade": len(t),
            "hit_rate": (t["rend_titolo"] > 0).mean() if len(t) else np.nan,
            "rendimento_medio_trade": t["rend_titolo"].mean() if len(t) else np.nan,
            "durata_media_giorni": t["giorni_holding"].mean() if len(t) else np.nan,
            "pnl_netto_portafoglio": t["pnl_netto"].sum(),
        })
    return pd.DataFrame(righe)


def sensibilita_costi(dati, segnali):
    """Rilancia la variante completa con costi per lato diversi (solo azioni). Analisi di robustezza."""
    global COSTO_PER_LATO
    base = COSTO_PER_LATO
    righe = []
    rend_spy = dati["spy"]["close"].pct_change()
    try:
        for bps in SENSIBILITA_COSTI_BPS:
            COSTO_PER_LATO = bps / 1e4
            for versione, copertura in VERSIONI.items():
                g = esegui_backtest(dati, segnali, copertura=copertura, **VARIANTI["4_Completa"])["giornaliero"]
                for periodo, maschera in periodi_di_analisi(g.index).items():
                    m = calcola_metriche(g[maschera], rend_spy)
                    righe.append({"costo_bps_per_lato": bps, "versione": versione, "periodo": periodo,
                                  "cagr": m.get("cagr"), "sharpe": m.get("sharpe"),
                                  "max_drawdown": m.get("max_drawdown")})
    finally:
        COSTO_PER_LATO = base            # ripristina sempre il valore di base
    return pd.DataFrame(righe)


def _salva_csv(df, nome, indice=False):
    CARTELLA_OUTPUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(CARTELLA_OUTPUT / nome, index=indice, sep=CSV_SEP, decimal=CSV_DECIMALE,
              encoding="utf-8-sig", float_format="%.6f")
    print(f"  salvato output/{nome}")


def genera_metriche_e_csv(dati, segnali, risultati):
    """Calcola tutte le metriche, stampa il riepilogo e scrive i CSV in output/."""
    print("\n--- Metriche e CSV ---")
    rend_spy = dati["spy"]["close"].pct_change()
    indice = next(iter(next(iter(risultati.values())).values()))["giornaliero"].index

    # 1-2. confronto varianti e metriche per periodo (in-sample / out-of-sample)
    righe = []
    for versione, varianti in risultati.items():
        for nome, r in varianti.items():
            for periodo, maschera in periodi_di_analisi(r["giornaliero"].index).items():
                m = calcola_metriche(r["giornaliero"][maschera], rend_spy)
                righe.append({"versione": versione, "variante": nome, "periodo": periodo, **m})
    for periodo, maschera in periodi_di_analisi(indice).items():
        m = calcola_metriche(metriche_spy(rend_spy, indice)[maschera], rend_spy)
        righe.append({"versione": "benchmark", "variante": "SPY", "periodo": periodo, **m})
    tabella = pd.DataFrame(righe)
    _salva_csv(tabella[tabella["periodo"] == "totale"], "confronto_varianti.csv")
    _salva_csv(tabella, "metriche_in_out_sample.csv")

    # 3. rendimenti giornalieri netti di tutte le serie (per il team Risk)
    ret = pd.DataFrame({"SPY": rend_spy.reindex(indice)})
    for versione, varianti in risultati.items():
        for nome, r in varianti.items():
            ret[f"{versione}__{nome}"] = r["giornaliero"]["ret_netto"]
    ret.index.name = "data"
    _salva_csv(ret, "rendimenti_giornalieri.csv", indice=True)
    for versione, varianti in risultati.items():          # dettaglio completo della variante finale
        _salva_csv(varianti["4_Completa"]["giornaliero"], f"dettaglio_giornaliero_{versione}.csv", indice=True)

    # 4. log di tutti i trade (identici nelle due versioni: la copertura non cambia le entrate)
    colonne = ["ticker", "lato", "data_segnale", "data_entrata", "data_uscita", "motivo_uscita",
               "giorni_holding", "peso", "z_entrata", "rsi_entrata", "prezzo_entrata",
               "rend_titolo", "pnl_lordo", "costi", "pnl_netto"]
    log = pd.concat([r["trades"][colonne].assign(variante=nome)
                     for nome, r in risultati["senza_copertura"].items()])
    _salva_csv(log, "log_trade.csv")

    # statistiche sui trade, per periodo di entrata
    st = []
    for nome, r in risultati["senza_copertura"].items():
        t = r["trades"]
        for periodo, maschera in periodi_di_analisi(pd.DatetimeIndex(t["data_entrata"])).items():
            st.append(statistiche_trade(t[np.asarray(maschera)]).assign(variante=nome, periodo=periodo))
    _salva_csv(pd.concat(st), "statistiche_trade.csv")

    # 5. sensibilita' ai costi
    sens = sensibilita_costi(dati, segnali)
    _salva_csv(sens, "sensibilita_costi.csv")

    # riepilogo a schermo
    print("\nVariante completa (netto dei costi):")
    chiavi = ["cagr", "volatilita", "sharpe", "max_drawdown", "beta_spy", "costi_annui"]
    vista = tabella[(tabella["variante"].isin(["4_Completa", "SPY"]))]
    vista = vista[["versione", "periodo"] + chiavi].copy()
    for c in ["cagr", "volatilita", "max_drawdown", "costi_annui"]:
        vista[c] = (vista[c] * 100).round(1).astype(str) + "%"
    print(vista.round(2).to_string(index=False))
    return tabella


# ======================================================================
# 5. GRAFICI
# ======================================================================

COLORI_VARIANTI = {"1_Generica": "#9e9e9e", "2_Settore": "#e69f00", "3_Volume": "#009e73",
                   "4_Completa": "#0072b2"}      # palette adatta anche a chi non distingue i colori
COLORE_SPY = "#222222"
TITOLI_VERSIONI = {"senza_copertura": "Senza copertura (long-biased)",
                   "con_copertura": "Con copertura SPY (market-neutral)"}


def _equity(rendimenti):
    """Curva del capitale con base 100 (rendimenti giornalieri composti)."""
    return 100 * (1 + rendimenti.fillna(0)).cumprod()


def _segna_out_of_sample(ax, indice):
    """Fissa l'asse sulle date del backtest e segna il periodo out-of-sample (linea e ombra grigia)."""
    fine = pd.Timestamp(FINE_IN_SAMPLE)
    ax.set_xlim(indice[0], indice[-1])
    ax.axvline(fine, color="#777777", linestyle="--", linewidth=0.9)
    ax.axvspan(fine, indice[-1], color="#000000", alpha=0.04)


def genera_grafici(dati, risultati):
    """Crea i grafici in output/: equity delle varianti contro SPY e dettaglio della variante completa."""
    import matplotlib
    matplotlib.use("Agg")                      # salva su file, senza aprire finestre
    import matplotlib.pyplot as plt

    CARTELLA_OUTPUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": 0.25})
    rend_spy = dati["spy"]["close"].pct_change()
    indice = next(iter(next(iter(risultati.values())).values()))["giornaliero"].index
    equity_spy = _equity(rend_spy.reindex(indice))

    # --- Grafico 1: equity delle 4 varianti contro SPY, una colonna per versione ---
    fig, assi = plt.subplots(1, len(risultati), figsize=(13, 4.8), sharey=True)
    for ax, (versione, varianti) in zip(np.atleast_1d(assi), risultati.items()):
        ax.plot(equity_spy.index, equity_spy, color=COLORE_SPY, linewidth=1.6, label="SPY (buy & hold)")
        for nome, r in varianti.items():
            e = _equity(r["giornaliero"]["ret_netto"])
            ax.plot(e.index, e, color=COLORI_VARIANTI[nome], linewidth=1.4, label=nome.replace("_", " "))
        ax.set_title(TITOLI_VERSIONI[versione])
        ax.set_ylabel("Valore del capitale (base 100, netto costi)")
        _segna_out_of_sample(ax, indice)
        ax.legend(loc="upper left", frameon=False)
    fig.suptitle("Equity line delle 4 varianti contro SPY (tratteggio: inizio out-of-sample)")
    fig.tight_layout()
    fig.savefig(CARTELLA_OUTPUT / "equity_varianti_vs_spy.png", dpi=150)
    plt.close(fig)
    print("  salvato output/equity_varianti_vs_spy.png")

    # --- Grafico 2: dettaglio della variante completa, una figura per versione ---
    for versione, varianti in risultati.items():
        g = varianti["4_Completa"]["giornaliero"]
        fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(10, 9), sharex=True,
                                         gridspec_kw={"height_ratios": [3, 2, 2]})
        e = _equity(g["ret_netto"])
        a1.plot(e.index, e, color=COLORI_VARIANTI["4_Completa"], linewidth=1.6, label="Variante completa")
        a1.plot(equity_spy.index, equity_spy, color=COLORE_SPY, linewidth=1.0, alpha=0.7, label="SPY")
        a1.set_ylabel("Capitale (base 100)")
        a1.set_title(f"Variante completa - {TITOLI_VERSIONI[versione]}")
        a1.legend(loc="upper left", frameon=False)

        dd = e / e.cummax() - 1
        a2.fill_between(dd.index, dd * 100, 0, color="#d55e00", alpha=0.6)
        a2.set_ylabel("Drawdown (%)")

        # le esposizioni cambiano molto da un giorno all'altro: si mostra la media mobile a 20 giorni
        mm = lambda serie: serie.rolling(20, min_periods=1).mean() * 100
        a3.plot(g.index, mm(g["gross"]), color="#0072b2", linewidth=1.3, label="Gross (titoli)")
        a3.plot(g.index, mm(g["net"]), color="#e69f00", linewidth=1.3, label="Net (solo titoli)")
        a3.plot(g.index, mm(g["net"] + g["copertura"]), color="#222222", linewidth=1.3,
                label="Net dopo copertura SPY")
        a3.axhline(0, color="#777777", linewidth=0.6)
        a3.set_ylabel("Esposizione (% capitale, media 20 gg)")
        a3.legend(loc="upper left", ncol=3, frameon=False)
        for ax in (a1, a2, a3):
            _segna_out_of_sample(ax, indice)
        fig.tight_layout()
        nome_file = f"variante_completa_{versione}.png"
        fig.savefig(CARTELLA_OUTPUT / nome_file, dpi=150)
        plt.close(fig)
        print(f"  salvato output/{nome_file}")


# ======================================================================
# MAIN
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description="Backtest short-term reversal VWAP+RSI")
    parser.add_argument("--demo", action="store_true", help="usa dati simulati")
    args = parser.parse_args()

    dati = carica_dati(demo=args.demo)
    riepilogo_dati(dati)
    segnali = calcola_segnali(dati)
    riepilogo_segnali(segnali)
    print("\n--- Backtest delle 4 varianti, nelle 2 versioni (senza/con copertura) ---")
    risultati = esegui_tutte_le_varianti(dati, segnali)
    genera_metriche_e_csv(dati, segnali, risultati)
    print("\n--- Grafici ---")
    genera_grafici(dati, risultati)


if __name__ == "__main__":
    main()
