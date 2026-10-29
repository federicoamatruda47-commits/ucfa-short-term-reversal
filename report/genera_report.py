# -*- coding: utf-8 -*-
"""
Genera il PDF di accompagnamento (logica, scelte, risultati, limiti) leggendo i CSV in output/.
Tutte le cifre dei risultati sono lette dai CSV, non scritte a mano.

Struttura pensata per essere reimpaginata dal team: sezioni numerate, tabelle e figure numerate,
stili semplici. Le figure usate nel PDF vengono salvate anche in report/img/.

Uso (dalla cartella del progetto):  python report/genera_report.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

RADICE = Path(__file__).resolve().parent.parent
OUT = RADICE / "output"
IMG = RADICE / "report" / "img"
PDF = RADICE / "report" / "Report_UCFA_short_term_reversal.pdf"
REPO_URL = "https://github.com/federicoamatruda47-commits/ucfa-short-term-reversal"
FINE_IN_SAMPLE = "2021-12-31"

# Arial supporta accenti e simboli matematici (<=, >=, meno) che i font standard non hanno
FONT_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic", str(FONT_DIR / "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", str(FONT_DIR / "arialbi.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                              italic="Arial-Italic", boldItalic="Arial-BoldItalic")

BLU = colors.HexColor("#0b3d6b")
GRIGIO = colors.HexColor("#f0f2f5")
BORDO = colors.HexColor("#c9ced6")
ARANCIO = colors.HexColor("#fff4e5")

S = {
    "titolo": ParagraphStyle("titolo", fontName="Arial-Bold", fontSize=20, leading=25, textColor=BLU, spaceAfter=6),
    "sotto": ParagraphStyle("sotto", fontName="Arial", fontSize=11, leading=15, textColor=colors.HexColor("#444444"), spaceAfter=3),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=14, leading=18, textColor=BLU, spaceBefore=14, spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11, leading=14, textColor=BLU, spaceBefore=8, spaceAfter=3, keepWithNext=1),
    "p": ParagraphStyle("p", fontName="Arial", fontSize=9.5, leading=13.5, alignment=TA_JUSTIFY, spaceAfter=5),
    "b": ParagraphStyle("b", fontName="Arial", fontSize=9.5, leading=13.5, leftIndent=12, bulletIndent=2, spaceAfter=2),
    "cella": ParagraphStyle("cella", fontName="Arial", fontSize=8, leading=10),
    "cellab": ParagraphStyle("cellab", fontName="Arial-Bold", fontSize=8, leading=10),
    "didascalia": ParagraphStyle("didascalia", fontName="Arial-Italic", fontSize=8, leading=10.5,
                                 textColor=colors.HexColor("#555555"), spaceBefore=2, spaceAfter=7),
    "titolo_tab": ParagraphStyle("titolo_tab", fontName="Arial-Bold", fontSize=8.5, leading=11,
                                 textColor=colors.HexColor("#333333"), spaceBefore=4, spaceAfter=2, keepWithNext=1),
    "box": ParagraphStyle("box", fontName="Arial", fontSize=9.5, leading=13.5, alignment=TA_JUSTIFY),
}


# ----------------------------------------------------------------------
# Utilita'
# ----------------------------------------------------------------------
def esc(testo):
    """Nei Paragraph la & va scritta &amp; (altrimenti sparisce o rompe il markup)."""
    return str(testo).replace("&", "&amp;")


def _formatta(valore, d):
    testo = f"{valore:.{d}f}"
    if float(testo) == 0:                     # niente "-0,00"
        testo = testo.lstrip("-")
    return testo.replace(".", ",").replace("-", "\u2212")


def pct(x, d=1):
    return _formatta(x * 100, d) + "%"


def num(x, d=2):
    return _formatta(x, d)


def P(testo, stile="p"):
    return Paragraph(esc(testo), S[stile])


def elenco(voci):
    return [Paragraph(esc(v), S["b"], bulletText="\u2022") for v in voci]


_contatori = {"Tabella": 0, "Figura": 0}


def titolo_tabella(testo):
    _contatori["Tabella"] += 1
    return P(f"Tabella {_contatori['Tabella']}. {testo}", "titolo_tab")


def didascalia(testo):
    _contatori["Figura"] += 1
    return P(f"Figura {_contatori['Figura']}. {testo}", "didascalia")


def tabella(righe, larghezze, intestazioni=1):
    """Tabella con testo a capo. righe: lista di liste di stringhe."""
    dati = []
    for i, r in enumerate(righe):
        stile = S["cellab"] if i < intestazioni else S["cella"]
        dati.append([Paragraph(esc(c), stile) for c in r])
    t = Table(dati, colWidths=larghezze, repeatRows=intestazioni)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, intestazioni - 1), GRIGIO),
        ("LINEBELOW", (0, 0), (-1, intestazioni - 1), 0.8, BLU),
        ("LINEBELOW", (0, intestazioni), (-1, -1), 0.3, BORDO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    return t


def riquadro(testo, sfondo=GRIGIO):
    t = Table([[Paragraph(esc(testo), S["box"])]], colWidths=[17 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), sfondo), ("BOX", (0, 0), (-1, -1), 0.6, BORDO),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def immagine(percorso, larghezza_cm=17):
    from PIL import Image as PILImage
    w, h = PILImage.open(percorso).size
    return Image(str(percorso), width=larghezza_cm * cm, height=larghezza_cm * cm * h / w)


def piede(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 8)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(2 * cm, 1.2 * cm, "UCFA Finance Society \u2013 Short-term reversal long/short su S&P 500")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Pagina {doc.page}")
    canvas.restoreState()


# ----------------------------------------------------------------------
# Dati dai CSV
# ----------------------------------------------------------------------
def leggi(nome):
    return pd.read_csv(OUT / nome, sep=";", decimal=",")


met = leggi("metriche_in_out_sample.csv")
trade = leggi("statistiche_trade.csv")
sens = leggi("sensibilita_costi.csv")
rend = leggi("rendimenti_giornalieri.csv")
rend["data"] = pd.to_datetime(rend["data"])
rend = rend.set_index("data")
det = {v: leggi(f"dettaglio_giornaliero_{v}.csv") for v in ["senza_copertura", "con_copertura"]}
for d in det.values():
    d["data"] = pd.to_datetime(d["data"])


def riga(versione, variante, periodo):
    return met[(met.versione == versione) & (met.variante == variante) & (met.periodo == periodo)].iloc[0]


NOMI_VARIANTI = {"1_Generica": "1. Generica (VWAP + RSI)", "2_Settore": "2. + Segnale relativo al settore",
                 "3_Volume": "3. + Filtro volume anomalo", "4_Completa": "4. + Filtro trimestrali (completa)"}
COLORI = {"1_Generica": "#9e9e9e", "2_Settore": "#e69f00", "3_Volume": "#009e73", "4_Completa": "#0072b2"}


# ----------------------------------------------------------------------
# Figure (rigenerate qui: la versione senza copertura non deve mostrare linee di copertura)
# ----------------------------------------------------------------------
IMG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})


def equity(r):
    return 100 * (1 + r.fillna(0)).cumprod()


def segna_oos(ax, indice):
    fine = pd.Timestamp(FINE_IN_SAMPLE)
    ax.set_xlim(indice[0], indice[-1])
    ax.axvline(fine, color="#777777", linestyle="--", linewidth=0.9)
    ax.axvspan(fine, indice[-1], color="#000000", alpha=0.04)


indice = rend.index
eq_spy = equity(rend["SPY"])

# Figura A: equity delle 4 varianti contro SPY (senza copertura)
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(eq_spy.index, eq_spy, color="#222222", linewidth=1.6, label="SPY (buy & hold)")
for var, col in COLORI.items():
    e = equity(rend[f"senza_copertura__{var}"])
    ax.plot(e.index, e, color=col, linewidth=1.4, label=NOMI_VARIANTI[var])
ax.set_ylabel("Capitale (base 100, netto costi)")
segna_oos(ax, indice)
ax.legend(loc="upper left", frameon=False)
fig.tight_layout()
fig.savefig(IMG / "equity_varianti_vs_spy.png", dpi=170)
plt.close(fig)


def figura_dettaglio(versione, nome_file, con_copertura):
    g = det[versione].set_index("data")
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(9, 8.2), sharex=True, gridspec_kw={"height_ratios": [3, 2, 2]})
    e = equity(g["ret_netto"])
    a1.plot(e.index, e, color=COLORI["4_Completa"], linewidth=1.6, label="Variante completa")
    a1.plot(eq_spy.index, eq_spy, color="#222222", linewidth=1.0, alpha=0.7, label="SPY")
    a1.set_ylabel("Capitale (base 100)")
    a1.legend(loc="upper left", frameon=False)
    dd = e / e.cummax() - 1
    a2.fill_between(dd.index, dd * 100, 0, color="#d55e00", alpha=0.6)
    a2.set_ylabel("Drawdown (%)")
    mm = lambda s: s.rolling(20, min_periods=1).mean() * 100
    a3.plot(g.index, mm(g["gross"]), color="#0072b2", linewidth=1.3, label="Gross")
    a3.plot(g.index, mm(g["net"]), color="#e69f00", linewidth=1.3, label="Net")
    if con_copertura:
        a3.plot(g.index, mm(g["net"] + g["copertura"]), color="#222222", linewidth=1.3, label="Net dopo copertura SPY")
    a3.axhline(0, color="#777777", linewidth=0.6)
    a3.set_ylabel("Esposizione (% capitale,\nmedia a 20 giorni)")
    a3.legend(loc="upper left", ncol=3, frameon=False)
    for a in (a1, a2, a3):
        segna_oos(a, g.index)
    fig.tight_layout()
    fig.savefig(IMG / nome_file, dpi=170)
    plt.close(fig)


figura_dettaglio("senza_copertura", "variante_completa_dettaglio.png", False)
figura_dettaglio("con_copertura", "appendice_variante_completa_con_copertura.png", True)

# Figura appendice: equity con copertura
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(eq_spy.index, eq_spy, color="#222222", linewidth=1.6, label="SPY (buy & hold)")
for var, col in COLORI.items():
    e = equity(rend[f"con_copertura__{var}"])
    ax.plot(e.index, e, color=col, linewidth=1.4, label=NOMI_VARIANTI[var])
ax.set_ylabel("Capitale (base 100, netto costi)")
segna_oos(ax, indice)
ax.legend(loc="upper left", frameon=False)
fig.tight_layout()
fig.savefig(IMG / "appendice_equity_con_copertura.png", dpi=170)
plt.close(fig)

# ----------------------------------------------------------------------
# Contenuto
# ----------------------------------------------------------------------
st = []
V = "senza_copertura"
c_in, c_out, c_tot = riga(V, "4_Completa", "in_sample"), riga(V, "4_Completa", "out_of_sample"), riga(V, "4_Completa", "totale")
spy_in, spy_out, spy_tot = riga("benchmark", "SPY", "in_sample"), riga("benchmark", "SPY", "out_of_sample"), riga("benchmark", "SPY", "totale")

st += [P("Short-term reversal long/short su S&P 500", "titolo"),
       P("Bande VWAP relative al settore, conferma RSI e filtri dalla letteratura accademica", "sotto"),
       P("Progetto di esercitazione \u2013 UCFA Finance Society, Universit\u00e0 Cattolica del Sacro Cuore, Milano", "sotto"),
       P("Autore: Federico Amatruda", "sotto"),
       P(f'Codice, dati e grafici: <a href="{REPO_URL}" color="#0b3d6b">{REPO_URL}</a>', "sotto"),
       Spacer(1, 8)]

# --- 1. Introduzione ---
st.append(P("1. Introduzione e obiettivo", "h1"))
st.append(P(
    "Il progetto costruisce e backtesta, dal 2016 a oggi, un fondo long/short equity sul mercato USA basato sulla short-term reversal. "
    "L\u2019idea \u00e8 che un titolo che si allontana molto dal suo prezzo medio recente (il VWAP) <i>rispetto al proprio settore</i>, e che "
    "un RSI conferma essere in eccesso, tende a rientrare nei giorni successivi. Il segnale si calcola alla chiusura del giorno d su dati giornalieri "
    "e il trade si esegue all\u2019apertura di d+1, senza look-ahead."))
st.append(riquadro(
    f"<b>Sintesi dei risultati.</b> Al netto dei costi, la variante completa ha un CAGR di {pct(c_in.cagr)} in-sample (2016\u20132021, Sharpe {num(c_in.sharpe)}) "
    f"e di {pct(c_out.cagr)} out-of-sample (2022\u2192oggi, Sharpe {num(c_out.sharpe)}), con drawdown massimo {pct(c_out.max_drawdown)} contro "
    f"{pct(spy_out.max_drawdown)} di SPY. Non batte SPY in rendimento assoluto: l\u2019obiettivo \u00e8 mostrare cosa aggiunge ogni scelta e quanto ne resta dopo i costi. "
    "<br/><b>Avvertenze.</b> I parametri sono stati scelti sull\u2019in-sample dopo circa 60 combinazioni provate (sezione 8); con le soglie finali il fondo \u00e8 molto selettivo "
    f"(in media {num(c_tot.n_long_medio, 1)} posizioni long e quasi nessuna short, gross medio {pct(c_tot.gross_medio, 0)} del capitale)."))

# --- 2. Letteratura ---
st.append(P("2. Supporto accademico", "h1"))
st.append(P("La short-term reversal \u00e8 un\u2019anomalia classica (i titoli che salgono di pi\u00f9 in un mese tendono a sottoperformare nel successivo e viceversa), "
            "ma la sua versione generica \u00e8 diventata debole sulle large cap. Quattro lavori motivano le scelte del progetto."))
st.append(titolo_tabella("Letteratura di riferimento e scelte conseguenti"))
st.append(tabella([
    ["Lavoro", "Evidenza", "Scelta nel progetto"],
    ["Stosik & Zaremba (2026, Economics Letters), <i>Short-term reversal persists globally \u2013 If properly measured</i>",
     "La reversal standard sugli USA rende circa zero; misurata rispetto al settore torna significativa. Dopo i costi il rendimento viene soprattutto dalla gamba long.",
     "Segnale relativo al settore GICS (z<sub>rel</sub>); gamba short limitata."],
    ["Blitz, van der Grient & Honarvar (2023, SSRN), <i>Reversing the Trend of Short-Term Reversal</i>",
     "La reversal generica \u00e8 sparita in USA ed Europa ma si recupera aggiustandola per settore o per fattori. I movimenti dovuti a notizie (trimestrali) non rientrano.",
     "Aggiustamento per settore; nessuna entrata dopo una trimestrale."],
    ["Medhat & Schmeling (2022, Review of Financial Studies), <i>Short-term Momentum</i>",
     "A 1 mese i titoli con basso volume mostrano reversal, quelli con volume molto alto momentum.",
     "Nessuna entrata sui titoli nel top 10% di volume relativo."],
    ["de Groot, Huij & Zhou (2012, Journal of Banking & Finance), <i>Another look at trading costs and short-term reversal profits</i>",
     "La reversal sopravvive ai costi sulle large cap se si limita il turnover, uscendo quando il segnale si neutralizza invece che a scadenza fissa.",
     "Uscita a take profit quando z<sub>rel</sub> rientra; attenzione al turnover (sezione 8)."],
], [5.2 * cm, 6.3 * cm, 5.5 * cm]))

# --- 3. Dati ---
st.append(P("3. Dati e universo", "h1"))
st += elenco([
    "<b>Universo:</b> costituenti attuali dell\u2019S&P 500 (lista da Wikipedia, con settore GICS), ticker convertiti per yfinance (BRK.B \u2192 BRK-B). 503 titoli, 11 settori.",
    "<b>Prezzi:</b> OHLCV giornalieri aggiustati per dividendi e split da yfinance, dal 2015. Il 2015 serve come riscaldamento degli indicatori; il backtest va dal 2016 a oggi.",
    "<b>Benchmark:</b> SPY.",
    "<b>Date delle trimestrali:</b> da yfinance; dove mancano si usa come proxy un giorno con volume superiore a 3 volte la media dei 60 giorni precedenti.",
    "<b>Cache:</b> i dati scaricati sono salvati su disco, per non riscaricarli a ogni lancio.",
])

# --- 4. Segnale ---
st.append(P("4. Costruzione del segnale", "h1"))
st.append(P("Su dati giornalieri, con finestra N = 20 giorni, per ogni titolo e ogni giorno:"))
st += elenco([
    "<b>Typical price:</b> TP = (High + Low + Close) / 3.",
    "<b>VWAP rolling:</b> VWAP = \u03a3(TP \u00b7 Volume) / \u03a3(Volume) sugli ultimi 20 giorni.",
    "<b>Deviazione standard pesata per volume:</b> \u03c3 = \u221a[ \u03a3(Volume \u00b7 TP\u00b2) / \u03a3(Volume) \u2212 VWAP\u00b2 ].",
    "<b>Distanza dal VWAP in deviazioni standard:</b> z = (Close \u2212 VWAP) / \u03c3.",
    "<b>Versione relativa al settore:</b> z<sub>rel</sub> = z \u2212 mediana di z tra i titoli dello stesso settore GICS quello stesso giorno. "
    "Se scende tutto il settore non c\u2019\u00e8 segnale: conta solo il movimento specifico del titolo.",
    "<b>Conferma:</b> RSI di Wilder a 14 periodi, calcolato non sul prezzo ma sulla serie z<sub>rel</sub>.",
])

# --- 5. Regole ---
st.append(P("5. Regole di trading", "h1"))
st.append(titolo_tabella("Regole operative e parametri finali"))
st.append(tabella([
    ["Elemento", "Regola"],
    ["Entrata long", "z<sub>rel</sub> \u2264 \u22121 e RSI < 25"],
    ["Entrata short", "z<sub>rel</sub> \u2265 +1 e RSI > 75; la gamba short non pu\u00f2 superare il 10% del capitale"],
    ["Priorit\u00e0", "Se i candidati superano la capacit\u00e0, si entra prima sui titoli con |z<sub>rel</sub>| pi\u00f9 alto"],
    ["Esclusione per volume anomalo", "Volume relativo (media a 5 giorni / media dei 60 giorni precedenti) nel top 10% dell\u2019universo quel giorno"],
    ["Esclusione per trimestrale", "Trimestrale negli ultimi 5 giorni di borsa (o picco di volume come proxy)"],
    ["Take profit", "z<sub>rel</sub> torna a 0, ma solo dopo almeno 3 giorni di holding"],
    ["Stop loss", "z<sub>rel</sub> peggiora di 1,5 deviazioni standard rispetto all\u2019entrata; vale sempre, anche nei primi giorni"],
    ["Time stop", "15 giorni di borsa. Nessun rientro sullo stesso titolo nel giorno in cui \u00e8 stato chiuso"],
    ["Sizing", "Peso = 8% / volatilit\u00e0 annualizzata (dev. standard a 60 giorni dei rendimenti log \u00d7 \u221a252), massimo 12% per titolo, fisso dall\u2019entrata all\u2019uscita"],
    ["Esposizione", "Gross massimo 150%; se una nuova posizione lo supererebbe non si apre. Nessun limite sul net"],
    ["Esecuzione", "Segnale alla chiusura di d, trade all\u2019apertura di d+1. Rendimento giornaliero = overnight (chiusura \u2192 apertura) sulle posizioni del giorno prima + intraday (apertura \u2192 chiusura) sulle posizioni aggiornate"],
    ["Costi", "10 bps per lato su ogni variazione di peso, pi\u00f9 0,5% annuo di prestito titoli sugli short"],
], [4 * cm, 13 * cm]))

# --- 6. Varianti ---
st.append(P("6. Le quattro varianti", "h1"))
st.append(P("Per mostrare quanto aggiunge ogni scelta, il backtest gira in quattro versioni, aggiungendo un miglioramento alla volta."))
st += elenco([
    "<b>1. Generica:</b> solo VWAP + RSI, con z non relativo al settore e nessun filtro.",
    "<b>2. + Settore:</b> segnale relativo al settore (z<sub>rel</sub>).",
    "<b>3. + Volume:</b> filtro sul volume anomalo.",
    "<b>4. + Trimestrali (completa):</b> filtro sulle trimestrali.",
])

# --- 7. Risultati ---
st.append(P("7. Risultati", "h1"))
st.append(P("Tutte le metriche sono al netto dei costi. Sharpe e Sortino sono calcolati con tasso privo di rischio pari a zero. "
            "In-sample: 2016\u20132021; out-of-sample: 2022\u2192oggi. I parametri sono stati scelti guardando solo l\u2019in-sample."))

st.append(P("7.1 Confronto tra le quattro varianti", "h2"))
righe = [["Variante", "CAGR", "Volat.", "Sharpe", "Sortino", "Max DD", "Calmar", "Costi annui", "Beta SPY"]]
for var, nome in NOMI_VARIANTI.items():
    r = riga(V, var, "totale")
    righe.append([nome, pct(r.cagr), pct(r.volatilita), num(r.sharpe), num(r.sortino), pct(r.max_drawdown), num(r.calmar),
                  pct(r.costi_annui), num(r.beta_spy)])
righe.append(["SPY (buy & hold)", pct(spy_tot.cagr), pct(spy_tot.volatilita), num(spy_tot.sharpe), num(spy_tot.sortino),
              pct(spy_tot.max_drawdown), num(spy_tot.calmar), "\u2013", "1,00"])
st.append(titolo_tabella("Le quattro varianti, periodo totale 2016\u2192oggi"))
st.append(tabella(righe, [5.1 * cm, 1.4 * cm, 1.4 * cm, 1.4 * cm, 1.5 * cm, 1.5 * cm, 1.4 * cm, 1.8 * cm, 1.5 * cm]))
st.append(P(
    "Ogni miglioramento aggiunge valore: il confronto con il settore recupera la reversal (la variante generica \u00e8 quasi piatta), "
    "il filtro sul volume riduce il drawdown e quello sulle trimestrali migliora ancora lo Sharpe.", "p"))
st.append(immagine(IMG / "equity_varianti_vs_spy.png", 15))
st.append(didascalia("Equity line delle quattro varianti contro SPY, base 100, netto dei costi. Il tratteggio segna l\u2019inizio dell\u2019out-of-sample."))

st.append(P("7.2 Variante completa: in-sample e out-of-sample", "h2"))
spy_rows = {"cagr", "volatilita", "sharpe", "sortino", "max_drawdown", "calmar"}
voci = [("CAGR", "cagr", pct), ("Volatilit\u00e0 annua", "volatilita", pct), ("Sharpe", "sharpe", num), ("Sortino", "sortino", num),
        ("Max drawdown", "max_drawdown", pct), ("Calmar", "calmar", num),
        ("Rendimento lordo annuo", "rendimento_lordo_annuo", pct), ("Costi annui", "costi_annui", pct),
        ("Turnover annuo (multiplo del capitale)", "turnover_annuo", lambda x: num(x, 1) + "\u00d7"),
        ("Gross medio", "gross_medio", lambda x: pct(x, 0)), ("Net medio", "net_medio_titoli", lambda x: pct(x, 0)),
        ("N. medio posizioni long", "n_long_medio", lambda x: num(x, 1)), ("N. medio posizioni short", "n_short_medio", lambda x: num(x, 2)),
        ("Beta rispetto a SPY", "beta_spy", num), ("Correlazione con SPY", "correlazione_spy", num)]


def tabella_metriche(versione, titolo_tab, extra=None):
    righe = [["Metrica", "In-sample 2016\u201321", "Out-of-sample 2022\u2192", "Totale", "SPY (totale)"]]
    for nome, chiave, f in voci:
        a, b, c = (riga(versione, "4_Completa", p) for p in ["in_sample", "out_of_sample", "totale"])
        s = f(spy_tot[chiave]) if chiave in spy_rows else ("1,00" if chiave in ("beta_spy", "correlazione_spy") else "\u2013")
        righe.append([nome, f(a[chiave]), f(b[chiave]), f(c[chiave]), s])
        if extra and chiave == "net_medio_titoli":
            righe.append(["Net medio dopo copertura SPY"] + [pct(riga(versione, "4_Completa", p).net_medio_con_copertura, 0)
                                                           for p in ["in_sample", "out_of_sample", "totale"]] + ["\u2013"])
    return [titolo_tabella(titolo_tab), tabella(righe, [6 * cm, 2.7 * cm, 3 * cm, 2.6 * cm, 2.7 * cm])]


st += tabella_metriche(V, "Metriche della variante completa per periodo")
st.append(P(
    f"Dal 2022 lo Sharpe scende da {num(c_in.sharpe)} a {num(c_out.sharpe)}: un calo atteso quando i parametri sono scelti sull\u2019in-sample. "
    "Il rendimento lordo annuo \u00e8 prima dei costi, mentre CAGR, volatilit\u00e0, Sharpe e drawdown sono dopo i costi.", "p"))
st.append(immagine(IMG / "variante_completa_dettaglio.png", 14))
st.append(didascalia("Variante completa: equity contro SPY, drawdown, gross e net exposure (media mobile a 20 giorni). Il tratteggio segna l\u2019inizio dell\u2019out-of-sample."))

st.append(P("7.3 Statistiche sui trade", "h2"))
nomi_g = {"tutti": "Tutti i trade", "lato_long": "Long", "lato_short": "Short", "uscita_take_profit": "Uscita: take profit",
          "uscita_stop_loss": "Uscita: stop loss", "uscita_time_stop": "Uscita: time stop", "uscita_aperta_a_fine": "Ancora aperti a fine periodo"}
t4 = trade[trade.variante == "4_Completa"]
righe = [["Gruppo", "N. totale", "di cui IS", "di cui OOS", "Hit rate", "Rend. medio", "Durata media (gg)", "Contributo P&L netto"]]
for g in nomi_g:
    tt = t4[(t4.gruppo == g) & (t4.periodo == "totale")].iloc[0]
    ni = int(t4[(t4.gruppo == g) & (t4.periodo == "in_sample")].iloc[0].n_trade)
    no = int(t4[(t4.gruppo == g) & (t4.periodo == "out_of_sample")].iloc[0].n_trade)
    ok = tt.n_trade > 0
    righe.append([nomi_g[g], f"{int(tt.n_trade)}", str(ni), str(no), pct(tt.hit_rate, 0) if ok else "\u2013",
                  pct(tt.rendimento_medio_trade) if ok else "\u2013", num(tt.durata_media_giorni, 1) if ok else "\u2013",
                  pct(tt.pnl_netto_portafoglio)])
st.append(titolo_tabella("Statistiche sui trade della variante completa (IS = in-sample, OOS = out-of-sample)"))
st.append(tabella(righe, [4 * cm, 1.8 * cm, 1.5 * cm, 1.6 * cm, 1.5 * cm, 1.9 * cm, 2.2 * cm, 2.5 * cm]))
n_short = int(t4[(t4.gruppo == "lato_short") & (t4.periodo == "totale")].iloc[0].n_trade)
n_tot = int(t4[(t4.gruppo == "tutti") & (t4.periodo == "totale")].iloc[0].n_trade)
st.append(P(
    "Hit rate e rendimento medio sono del titolo (con il segno del lato), prima dei costi; il contributo al P&L \u00e8 al netto dei costi, come quota del capitale. "
    f"I take profit guadagnano, i time stop e gli stop loss restituiscono una parte del guadagno. <b>I trade sono pochi</b>: {n_tot} in dieci anni, di cui solo {n_short} short; "
    "il fondo \u00e8 in pratica long-only con una piccola gamba short.", "didascalia"))

st.append(P("7.4 Sensibilit\u00e0 ai costi", "h2"))
st.append(P("I 10 bps per lato sono un\u2019ipotesi prudente per le large cap. La variante completa \u00e8 stata rilanciata con costi diversi sulle sole azioni, a parametri invariati."))
righe = [["Costo per lato", "CAGR in-sample", "Sharpe in-sample", "CAGR out-of-sample", "Sharpe out-of-sample"]]
for bps in sorted(sens.costo_bps_per_lato.unique(), reverse=True):
    a = sens[(sens.costo_bps_per_lato == bps) & (sens.versione == V) & (sens.periodo == "in_sample")].iloc[0]
    b = sens[(sens.costo_bps_per_lato == bps) & (sens.versione == V) & (sens.periodo == "out_of_sample")].iloc[0]
    righe.append([f"{int(bps)} bps" + (" (caso base)" if bps == 10 else ""), pct(a.cagr), num(a.sharpe), pct(b.cagr), num(b.sharpe)])
st.append(titolo_tabella("Variante completa con costi per lato diversi"))
st.append(tabella(righe, [3.6 * cm, 3.2 * cm, 3.2 * cm, 3.6 * cm, 3.4 * cm]))

# --- 8. Calibrazione ---
st.append(P("8. Come siamo arrivati ai parametri", "h1"))
st.append(P(
    "I parametri iniziali erano quelli della traccia. Il primo backtest sui dati reali perdeva soldi al netto dei costi, con costi di circa il 5% annuo "
    "dovuti a un turnover di circa 50 volte il capitale. Da l\u00ec abbiamo provato, una leva alla volta, <b>solo sul periodo in-sample 2016\u20132021</b>, "
    "guardando il 2022 in poi solo a scelte fatte. La tabella riporta lo Sharpe in-sample della variante completa senza copertura. "
    "In tutto sono state provate circa 60 combinazioni, quindi i risultati in-sample sono in parte frutto della selezione."))
st.append(titolo_tabella("Leve provate sul periodo in-sample (Sharpe) e scelta finale"))
st.append(tabella([
    ["Leva", "Valori provati \u2192 Sharpe in-sample", "Scelta"],
    ["Tetto sugli short", "0%: 0,61 \u00b7 10%: 0,36 \u00b7 25%: 0,01 \u00b7 50%: \u22120,41 \u00b7 nessun tetto: \u22120,67",
     "10% (mantiene una gamba short, anche se 0% sarebbe migliore)"],
    ["Sizing (rischio target / peso massimo)", "1%/5%: 0,36 \u00b7 2%/5%: 0,57 \u00b7 3%/8%: 0,70 \u00b7 4%/8%: 0,78 \u00b7 5%/10%: 0,66", "4%/8%, poi rifatto"],
    ["Soglia di entrata |z<sub>rel</sub>|", "1,0: 0,78 \u00b7 1,25: 0,71 \u00b7 1,5: 0,74 \u00b7 2,0: 0,66", "Resta 1,0"],
    ["Soglia di take profit (z<sub>rel</sub>)", "0: 0,78 \u00b7 0,25: 0,75 \u00b7 0,5: 0,64 \u00b7 0,75: 0,51", "Resta 0"],
    ["Filtro volume: quota esclusa", "top 10%: 0,78 \u00b7 20%: 0,60 \u00b7 30%: 0,36 \u00b7 50%: 0,33", "Resta top 10%"],
    ["Distanza minima dal VWAP (filtro sui costi)", "0%: 0,78 \u00b7 0,5%: 0,74 \u00b7 1%: 0,72 \u00b7 1,5%: 0,77 \u00b7 2%: 0,68 \u00b7 3%: 0,66", "Non adottato"],
    ["<b>Soglie RSI</b> (costi annui)",
     "30/70: 0,78 (5,0%) \u00b7 28/72: 0,64 (3,3%) \u00b7 27/73: 0,72 (2,4%) \u00b7 26/74: 0,67 (1,8%) \u00b7 25/75: 0,90 (1,3%) \u00b7 24/76: 0,71 (0,9%) \u00b7 22/78: 0,46 (0,4%)",
     "<b>25/75</b>: riduce i costi in modo graduale"],
    ["Time stop (con RSI 30/70)", "10 giorni: 0,78 \u00b7 15: 0,90 \u00b7 20: 0,86", "15 giorni"],
    ["Sizing rifatto (RSI 25/75, time stop 15)", "4%/8%: 1,12 \u00b7 6%/10%: 1,26 \u00b7 8%/12%: 1,50 \u00b7 10%/15%: 1,50 \u00b7 12%/15%: 1,52", "8%/12%"],
], [4.4 * cm, 8.6 * cm, 4 * cm]))
st.append(P(
    "<b>Cosa abbiamo imparato.</b> (a) I costi sono il problema principale: la leva che ha funzionato \u00e8 ridurre il turnover restringendo la conferma RSI, "
    "in linea con de Groot et al. (b) Filtri pi\u00f9 severi su volume e trimestrali non aiutano oltre la soglia iniziale. "
    "(c) Gli short peggiorano il risultato a ogni dimensione, coerente con Stosik & Zaremba: il rendimento viene dalla gamba long.", "p"))

# --- 9. Verifica ---
st.append(P("9. Verifica del P&L", "h1"))
st.append(P(
    "Prima di produrre le metriche, il codice ricostruisce il P&L giornaliero usando solo il log dei trade (data e prezzo di entrata e uscita, lato, peso) "
    "e lo confronta con quello calcolato dal motore di backtest, insieme a costi e turnover. Se la differenza supera 10<super>\u221210</super> il programma si ferma con un errore. "
    "Su tutte le combinazioni la differenza massima \u00e8 dell\u2019ordine di 10<super>\u221216</super>."))

# --- 10. Limiti ---
st.append(P("10. Limiti", "h1"))
st += elenco([
    "<b>Survivorship bias:</b> si usano i costituenti di oggi dell\u2019S&P 500, quindi mancano i titoli usciti dall\u2019indice nel periodo; questo tende a migliorare i risultati.",
    "<b>Storico delle date delle trimestrali incompleto:</b> dove mancano si usa il proxy sul volume, meno preciso.",
    "<b>Costi semplificati:</b> 10 bps per lato senza market impact.",
    "<b>Confronto settoriale grossolano:</b> 11 settori GICS; un livello pi\u00f9 fine sarebbe pi\u00f9 preciso ma ogni gruppo avrebbe pochi titoli.",
    "<b>Filtro di valutazione non incluso:</b> la traccia prevedeva un filtro su EV/EBITDA e P/B, ma yfinance fornisce solo multipli attuali e non uno storico affidabile e completo; "
    "applicarli a tutto il periodo avrebbe introdotto un look-ahead (multipli di oggi applicati al passato).",
    "<b>Selezione dei parametri:</b> circa 60 combinazioni provate sull\u2019in-sample; i risultati in-sample sono ottimistici.",
    "<b>Pochi trade e posizioni:</b> in media 2\u20133 posizioni aperte e quasi nessuno short; la diversificazione \u00e8 bassa e un singolo titolo pu\u00f2 pesare fino al 12%.",
])

# --- 11. Conclusioni ---
st.append(P("11. Conclusioni", "h1"))
st.append(P(
    "La short-term reversal sulle large cap USA, misurata rispetto al settore, produce un segnale reale ma piccolo, che i costi di negoziazione assorbono facilmente. "
    "I risultati confermano le indicazioni dei quattro lavori: il confronto con il settore recupera la reversal che la versione generica non cattura, "
    "i filtri su volume e trimestrali riducono il rischio, il rendimento viene dalla gamba long e il turnover \u00e8 il vero nemico. "
    f"Dopo aver ridotto i costi a circa {pct(c_tot.costi_annui)} l\u2019anno, la variante completa ha un CAGR di {pct(c_out.cagr)} fuori campione, contro {pct(spy_out.cagr)} di SPY. "
    "Il rendimento \u00e8 modesto; il valore del lavoro sta nel metodo e nella misura di ogni scelta."))

# --- Appendice A ---
st.append(PageBreak())
st.append(P("Appendice A. Copertura del mercato con l\u2019ETF SPY (solo a scopo illustrativo)", "h1"))
st.append(riquadro(
    "<b>Questa appendice ha solo scopo illustrativo.</b> La strategia presentata nel documento \u00e8 quella delle sezioni 1\u201311, senza copertura. "
    "La copertura con SPY \u00e8 stata provata per mostrare cosa resta del segnale una volta tolta la componente di mercato; "
    "i suoi costi sono ipotesi e non dati osservati.", ARANCIO))
st.append(Spacer(1, 6))
st.append(P(
    "Il fondo senza copertura \u00e8 di fatto long-biased: il net medio \u00e8 positivo e il rendimento dipende in parte dal mercato. La versione illustrativa vende ogni giorno SPY "
    "(ETF dell\u2019S&P 500, trattato come un titolo) per un valore pari al beta del portafoglio, stimato come somma dei beta a 60 giorni di ogni posizione moltiplicati per il loro peso. "
    "La copertura si aggiorna solo se la variazione supera il 5% del capitale. Costi ipotizzati: 2 bps per lato e 0,25% annuo di prestito, perch\u00e9 SPY \u00e8 molto pi\u00f9 liquido delle azioni singole. "
    "In un fondo reale la copertura si farebbe con future sull\u2019indice, pi\u00f9 economici; qui sono esclusi per semplicit\u00e0."))
righe = [["Variante", "CAGR", "Volat.", "Sharpe", "Max DD", "Beta SPY"]]
for var, nome in NOMI_VARIANTI.items():
    r = riga("con_copertura", var, "totale")
    righe.append([nome, pct(r.cagr), pct(r.volatilita), num(r.sharpe), pct(r.max_drawdown), num(r.beta_spy)])
st.append(titolo_tabella("Appendice A: le quattro varianti con copertura SPY, periodo totale"))
st.append(tabella(righe, [6.2 * cm, 2 * cm, 2 * cm, 2 * cm, 2.2 * cm, 2.6 * cm]))
st += tabella_metriche("con_copertura", "Appendice A: metriche della variante completa con copertura SPY", extra=True)
st.append(P(
    "Con la copertura il beta va a circa zero e la volatilit\u00e0 si riduce, ma il rendimento cala: tolta la componente di mercato il segnale, al netto dei costi, ha un contributo molto piccolo, "
    "soprattutto fuori campione.", "p"))
st.append(immagine(IMG / "appendice_equity_con_copertura.png", 15))
st.append(didascalia("Appendice A: equity delle quattro varianti con copertura SPY contro SPY (illustrativo)."))
st.append(immagine(IMG / "appendice_variante_completa_con_copertura.png", 14))
st.append(didascalia("Appendice A: variante completa con copertura SPY. \u201cNet dopo copertura SPY\u201d \u00e8 il net in valore dopo la vendita di SPY (illustrativo)."))

# --- Appendice B ---
st.append(P("Appendice B. Materiale allegato", "h1"))
st.append(P(f'Tutti i file sono nel repository: <a href="{REPO_URL}" color="#0b3d6b">{REPO_URL}</a> (cartella <i>output</i>). '
            "I CSV usano il punto e virgola come separatore e la virgola come decimale."))
st.append(titolo_tabella("File allegati"))
st.append(tabella([
    ["File", "Contenuto"],
    ["confronto_varianti.csv", "Metriche delle quattro varianti (periodo totale), con SPY"],
    ["metriche_in_out_sample.csv", "Stesse metriche per periodo: totale, in-sample, out-of-sample"],
    ["rendimenti_giornalieri.csv", "Rendimenti giornalieri netti di tutte le serie (per il team Risk)"],
    ["dettaglio_giornaliero_*.csv", "Rendimento lordo, costi, gross e net giorno per giorno della variante completa"],
    ["log_trade.csv, statistiche_trade.csv", "Log di tutti i trade e statistiche per lato e motivo di uscita"],
    ["sensibilita_costi.csv", "Variante completa con costi di 10, 5, 3 e 2 bps per lato"],
    ["report/img/*.png", "Grafici usati nel documento, in alta risoluzione"],
], [6 * cm, 11 * cm]))

doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                        bottomMargin=2 * cm, title="Short-term reversal long/short su S&P 500",
                        author="Federico Amatruda", subject="UCFA Finance Society")
doc.build(st, onFirstPage=piede, onLaterPages=piede)
print("PDF creato:", PDF)
