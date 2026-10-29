# -*- coding: utf-8 -*-
"""
Genera il PDF di accompagnamento (logica, scelte, risultati, limiti) leggendo i CSV in output/.
Tutte le cifre dei risultati sono lette dai CSV, non scritte a mano.

Uso (dalla cartella del progetto):  python report/genera_report.py
"""
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

RADICE = Path(__file__).resolve().parent.parent
OUT = RADICE / "output"
PDF = RADICE / "report" / "Report_UCFA_short_term_reversal.pdf"
REPO_URL = "https://github.com/federicoamatruda47-commits/ucfa-short-term-reversal"

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

S = {
    "titolo": ParagraphStyle("titolo", fontName="Arial-Bold", fontSize=20, leading=25, textColor=BLU, spaceAfter=6),
    "sotto": ParagraphStyle("sotto", fontName="Arial", fontSize=11, leading=15, textColor=colors.HexColor("#444444"), spaceAfter=3),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=14, leading=18, textColor=BLU, spaceBefore=14, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11, leading=14, textColor=BLU, spaceBefore=8, spaceAfter=3),
    "p": ParagraphStyle("p", fontName="Arial", fontSize=9.5, leading=13.5, alignment=TA_JUSTIFY, spaceAfter=5),
    "b": ParagraphStyle("b", fontName="Arial", fontSize=9.5, leading=13.5, leftIndent=12, bulletIndent=2, spaceAfter=2),
    "cella": ParagraphStyle("cella", fontName="Arial", fontSize=8, leading=10),
    "cellab": ParagraphStyle("cellab", fontName="Arial-Bold", fontSize=8, leading=10),
    "nota": ParagraphStyle("nota", fontName="Arial-Italic", fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"), spaceAfter=6),
    "box": ParagraphStyle("box", fontName="Arial", fontSize=9.5, leading=13.5, alignment=TA_JUSTIFY),
}


# ----------------------------------------------------------------------
# Utilita'
# ----------------------------------------------------------------------
def pct(x, d=1):
    return f"{x * 100:.{d}f}%".replace(".", ",").replace("-", "\u2212")


def num(x, d=2):
    return f"{x:.{d}f}".replace(".", ",").replace("-", "\u2212")


def esc(testo):
    """Nei Paragraph la & va scritta &amp; (altrimenti sparisce o rompe il markup)."""
    return str(testo).replace("&", "&amp;")


def P(testo, stile="p"):
    return Paragraph(esc(testo), S[stile])


def elenco(voci):
    return [Paragraph(esc(v), S["b"], bulletText="\u2022") for v in voci]


def tabella(righe, larghezze, intestazioni=1, allinea_dx_da=1, zebra=True):
    """Tabella con testo a capo. righe: lista di liste di stringhe."""
    dati = []
    for i, r in enumerate(righe):
        stile = S["cellab"] if i < intestazioni else S["cella"]
        dati.append([Paragraph(esc(c), stile) for c in r])
    t = Table(dati, colWidths=larghezze, repeatRows=intestazioni)
    st = [("BACKGROUND", (0, 0), (-1, intestazioni - 1), GRIGIO),
          ("LINEBELOW", (0, 0), (-1, intestazioni - 1), 0.8, BLU),
          ("LINEBELOW", (0, intestazioni), (-1, -1), 0.3, BORDO),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    t.setStyle(TableStyle(st))
    return t


def immagine(nome, larghezza_cm=17):
    from PIL import Image as PILImage
    percorso = OUT / nome
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


def riga(versione, variante, periodo):
    return met[(met.versione == versione) & (met.variante == variante) & (met.periodo == periodo)].iloc[0]


NOMI_VERSIONI = {"senza_copertura": "Senza copertura", "con_copertura": "Con copertura SPY"}
NOMI_VARIANTI = {"1_Generica": "1 Generica", "2_Settore": "2 + Settore", "3_Volume": "3 + Volume",
                 "4_Completa": "4 Completa (+ Trimestrali)"}

# ----------------------------------------------------------------------
# Contenuto
# ----------------------------------------------------------------------
st = []
c_in = riga("senza_copertura", "4_Completa", "in_sample")
c_out = riga("senza_copertura", "4_Completa", "out_of_sample")
n_in = riga("con_copertura", "4_Completa", "in_sample")
n_out = riga("con_copertura", "4_Completa", "out_of_sample")
spy_out = riga("benchmark", "SPY", "out_of_sample")
spy_tot = riga("benchmark", "SPY", "totale")
c_tot = riga("senza_copertura", "4_Completa", "totale")
n_tot = riga("con_copertura", "4_Completa", "totale")

st += [P("Short-term reversal long/short su S&P 500", "titolo"),
       P("Bande VWAP relative al settore, conferma RSI e filtri dalla letteratura accademica", "sotto"),
       P("Progetto di esercitazione \u2013 UCFA Finance Society, Universit\u00e0 Cattolica del Sacro Cuore, Milano", "sotto"),
       P("Autore: Federico Amatruda  \u00b7  Codice e dati: " + f'<a href="{REPO_URL}" color="#0b3d6b">{REPO_URL}</a>', "sotto"),
       Spacer(1, 10)]

# --- 1. Sintesi ---
st.append(P("1. Sintesi", "h1"))
sintesi = (
    "Abbiamo costruito e backtestato, dal 2016 a oggi, una strategia di short-term reversal sulle azioni dell\u2019S&P 500. "
    "Un titolo che si allontana molto dal suo prezzo medio recente (VWAP) <i>rispetto al proprio settore</i>, e che l\u2019RSI "
    "conferma essere in eccesso, tende a rientrare nei giorni successivi. Il segnale usa dati giornalieri di yfinance, "
    "decide alla chiusura del giorno d ed esegue all\u2019apertura di d+1.<br/><br/>"
    f"<b>Risultato.</b> Al netto dei costi, la versione senza copertura del mercato ottiene un CAGR di {pct(c_in.cagr)} in-sample (2016\u20132021, "
    f"Sharpe {num(c_in.sharpe)}) e di {pct(c_out.cagr)} out-of-sample (2022\u2192oggi, Sharpe {num(c_out.sharpe)}), con un drawdown massimo di "
    f"{pct(c_out.max_drawdown)} contro {pct(spy_out.max_drawdown)} di SPY. La versione market-neutral (copertura con l\u2019ETF SPY) "
    f"ottiene {pct(n_in.cagr)} in-sample e {pct(n_out.cagr)} out-of-sample, con beta vicino a zero. "
    "Nessuna delle due batte SPY in rendimento assoluto: l\u2019obiettivo del lavoro \u00e8 mostrare, passo dopo passo, "
    "cosa aggiunge ogni scelta e quanto ne resta dopo i costi.<br/><br/>"
    "<b>Caveat principale.</b> I parametri sono stati scelti guardando solo l\u2019in-sample, ma dopo circa 60 combinazioni provate; "
    "il risultato in-sample \u00e8 in parte frutto di questa selezione e il calo fuori campione lo conferma. "
    "Inoltre, con le soglie scelte il fondo \u00e8 molto selettivo: in media 2,4 posizioni long e praticamente nessuna short, "
    "con un gross medio di circa il 29% del capitale."
)
t = Table([[Paragraph(esc(sintesi), S["box"])]], colWidths=[17 * cm])
t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GRIGIO), ("BOX", (0, 0), (-1, -1), 0.6, BORDO),
                       ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                       ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
st.append(t)

# --- 2. Letteratura ---
st.append(P("2. Idea e supporto accademico", "h1"))
st.append(P(
    "La short-term reversal (i titoli che salgono di pi\u00f9 in un mese tendono a sottoperformare nel successivo, e viceversa) "
    "\u00e8 un\u2019anomalia classica, ma la sua versione \u201cgenerica\u201d \u00e8 diventata debole sulle large cap. "
    "Quattro lavori guidano le scelte del progetto:"))
st.append(tabella([
    ["Lavoro", "Evidenza", "Scelta nel progetto"],
    ["Stosik & Zaremba (2026, Economics Letters), <i>Short-term reversal persists globally \u2013 If properly measured</i>",
     "La reversal standard sugli USA rende circa zero; misurata rispetto al settore torna significativa. Dopo i costi il rendimento viene soprattutto dalla gamba long.",
     "Segnale relativo al settore GICS (z<sub>rel</sub>). Gamba short limitata."],
    ["Blitz, van der Grient & Honarvar (2023, SSRN), <i>Reversing the Trend of Short-Term Reversal</i>",
     "La reversal generica \u00e8 sparita in USA ed Europa, ma si recupera aggiustandola per settore o per fattori. I movimenti dovuti a notizie (trimestrali) non rientrano.",
     "Aggiustamento per settore; filtro che esclude le entrate dopo una trimestrale."],
    ["Medhat & Schmeling (2022, Review of Financial Studies), <i>Short-term Momentum</i>",
     "A 1 mese i titoli con basso volume mostrano reversal, quelli con volume molto alto momentum.",
     "Nessuna entrata sui titoli nel top 10% di volume relativo."],
    ["de Groot, Huij & Zhou (2012, Journal of Banking & Finance), <i>Another look at trading costs and short-term reversal profits</i>",
     "La reversal sopravvive ai costi sulle large cap se si limita il turnover, uscendo quando il segnale si neutralizza invece che a scadenza fissa.",
     "Uscita a take profit quando z<sub>rel</sub> rientra; attenzione al turnover (sezione 7)."],
], [5.2 * cm, 6.3 * cm, 5.5 * cm]))

# --- 3. Dati ---
st.append(P("3. Dati e universo", "h1"))
st += elenco([
    "<b>Universo:</b> costituenti attuali dell\u2019S&P 500 (lista da Wikipedia, con settore GICS), ticker convertiti per yfinance (BRK.B \u2192 BRK-B). 503 titoli, 11 settori.",
    "<b>Prezzi:</b> OHLCV giornalieri aggiustati per dividendi e split da yfinance, dal 2015. Il 2015 serve come riscaldamento degli indicatori; il backtest parte dal 2016.",
    "<b>Benchmark:</b> SPY.",
    "<b>Date delle trimestrali:</b> da yfinance; dove mancano si usa come proxy un giorno con volume superiore a 3 volte la media dei 60 giorni precedenti.",
    "<b>Cache:</b> tutti i dati scaricati sono salvati su disco, per non riscaricarli a ogni lancio.",
])

# --- 4. Segnale ---
st.append(P("4. Il segnale", "h1"))
st.append(P(
    "Su dati giornalieri, con finestra N = 20 giorni, per ogni titolo e ogni giorno:"))
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
st.append(P("5. Regole operative", "h1"))
st.append(tabella([
    ["Elemento", "Regola (parametri finali)"],
    ["Entrata long", "z<sub>rel</sub> \u2264 \u22121 e RSI < 25"],
    ["Entrata short", "z<sub>rel</sub> \u2265 +1 e RSI > 75 (gamba short limitata al 10% del capitale)"],
    ["Priorit\u00e0", "Se i candidati superano la capacit\u00e0, si entra prima sui titoli con |z<sub>rel</sub>| pi\u00f9 alto"],
    ["Esclusione per volume", "Volume relativo (media 5 giorni / media dei 60 giorni precedenti) nel top 10% dell\u2019universo quel giorno"],
    ["Esclusione per trimestrale", "Trimestrale negli ultimi 5 giorni di borsa (o picco di volume come proxy)"],
    ["Take profit", "z<sub>rel</sub> torna a 0, ma solo dopo almeno 3 giorni di holding"],
    ["Stop loss", "z<sub>rel</sub> peggiora di 1,5 deviazioni standard rispetto all\u2019entrata; vale sempre"],
    ["Time stop", "15 giorni di borsa. Nessun rientro sullo stesso titolo nel giorno in cui \u00e8 stato chiuso"],
    ["Sizing", "Peso = 8% / volatilit\u00e0 annualizzata (dev. standard a 60 giorni dei rendimenti log \u00d7 \u221a252), massimo 12% per titolo, fisso fino all\u2019uscita"],
    ["Esposizione", "Gross massimo 150%; se una nuova posizione lo supererebbe, non si apre. Nessun limite sul net"],
    ["Esecuzione", "Segnale alla chiusura di d, trade all\u2019apertura di d+1 (nessun look-ahead). Rendimento giornaliero = overnight sulle posizioni del giorno prima + intraday sulle posizioni aggiornate"],
    ["Costi", "10 bps per lato su ogni variazione di peso, pi\u00f9 0,5% annuo di prestito titoli sugli short"],
], [4 * cm, 13 * cm]))

st.append(P("Copertura con l\u2019ETF SPY (seconda versione del fondo)", "h2"))
st.append(P(
    "Il fondo senza copertura \u00e8 di fatto long-biased: il net medio \u00e8 positivo e il rendimento dipende in parte dal mercato. "
    "La seconda versione vende ogni giorno SPY (ETF dell\u2019S&P 500, trattato come un titolo) per un valore pari al beta del portafoglio, "
    "stimato come somma dei beta a 60 giorni di ogni posizione, ciascuno moltiplicato per il suo peso. La copertura si aggiorna solo se la variazione "
    "supera il 5% del capitale. Costi ipotizzati: 2 bps per lato e 0,25% annuo di prestito, perch\u00e9 SPY \u00e8 molto pi\u00f9 liquido delle azioni singole. "
    "Sono ipotesi dichiarate, non dati osservati. In produzione la copertura si farebbe con future sull\u2019indice; li abbiamo esclusi per semplicit\u00e0."))

# --- 6. Varianti ---
st.append(P("6. Le quattro varianti", "h1"))
st.append(P(
    "Per mostrare quanto aggiunge ogni scelta, il backtest gira in quattro versioni, aggiungendo un miglioramento alla volta: "
    "(1) generica, solo VWAP + RSI con z non relativo al settore e nessun filtro; (2) + segnale relativo al settore; "
    "(3) + filtro sul volume anomalo; (4) + filtro sulle trimestrali (versione completa)."))

# --- 7. Percorso parametri ---
st.append(P("7. Come siamo arrivati ai parametri", "h1"))
st.append(P(
    "I parametri iniziali erano quelli della traccia. Il primo backtest sui dati reali perdeva soldi al netto dei costi "
    "(circa \u221238%\u2005come somma dei rendimenti giornalieri nella variante completa), con costi di circa il 5% annuo "
    "dovuti a un turnover di circa 50 volte il capitale. Da l\u00ec abbiamo provato, una leva alla volta, "
    "<b>solo sul periodo in-sample 2016\u20132021</b>, e abbiamo guardato il 2022 in poi solo a scelte fatte. "
    "La tabella riporta lo Sharpe in-sample della variante completa senza copertura (le altre leve sono tenute fisse a quanto indicato). "
    "Abbiamo provato circa 60 combinazioni in tutto: questo va tenuto presente nel leggere i risultati."))
st.append(tabella([
    ["Leva (periodo 2016\u20132021)", "Valori provati \u2192 Sharpe in-sample", "Scelta"],
    ["Tetto sugli short (parametri iniziali di sizing)", "0%: 0,61 \u00b7 10%: 0,36 \u00b7 25%: 0,01 \u00b7 50%: \u22120,41 \u00b7 nessun tetto: \u22120,67",
     "10%. Meglio sarebbe 0% (solo long), ma si \u00e8 mantenuta una gamba short"],
    ["Sizing (rischio target / peso massimo)", "1%/5%: 0,36 \u00b7 2%/5%: 0,57 \u00b7 3%/8%: 0,70 \u00b7 4%/8%: 0,78 \u00b7 5%/10%: 0,66",
     "4%/8% (poi rifatto, vedi sotto)"],
    ["Soglia di entrata |z<sub>rel</sub>|", "1,0: 0,78 \u00b7 1,25: 0,71 \u00b7 1,5: 0,74 \u00b7 2,0: 0,66", "Resta 1,0 (nessun miglioramento)"],
    ["Soglia di take profit (z<sub>rel</sub>)", "0: 0,78 \u00b7 0,25: 0,75 \u00b7 0,5: 0,64 \u00b7 0,75: 0,51", "Resta 0"],
    ["Filtro volume: quota esclusa", "top 10%: 0,78 \u00b7 20%: 0,60 \u00b7 30%: 0,36 \u00b7 50%: 0,33", "Resta top 10% (filtri pi\u00f9 larghi peggiorano)"],
    ["Distanza minima dal VWAP (filtro costi)", "0%: 0,78 \u00b7 0,5%: 0,74 \u00b7 1%: 0,72 \u00b7 1,5%: 0,77 \u00b7 2%: 0,68 \u00b7 3%: 0,66", "Non adottato (nessun miglioramento)"],
    ["<b>Soglie RSI</b> (costi annui in parentesi)",
     "30/70: 0,78 (5,0%) \u00b7 28/72: 0,64 (3,3%) \u00b7 27/73: 0,72 (2,4%) \u00b7 26/74: 0,67 (1,8%) \u00b7 25/75: 0,90 (1,3%) \u00b7 24/76: 0,71 (0,9%) \u00b7 22/78: 0,46 (0,4%)",
     "<b>25/75</b>: riduce molto i costi in modo graduale, non \u00e8 un picco isolato"],
    ["Time stop (con RSI 30/70)", "10 giorni: 0,78 \u00b7 15: 0,90 \u00b7 20: 0,86", "15 giorni"],
    ["Sizing rifatto (con RSI 25/75, time stop 15)", "4%/8%: 1,12 \u00b7 6%/10%: 1,26 \u00b7 8%/12%: 1,50 \u00b7 10%/15%: 1,50 \u00b7 12%/15%: 1,52", "8%/12% (inizio del plateau)"],
], [4.6 * cm, 8.4 * cm, 4 * cm]))
st.append(P(
    "<b>Cosa abbiamo imparato.</b> (a) I costi sono il problema principale: la leva che ha funzionato \u00e8 stata ridurre il turnover "
    "restringendo la conferma RSI, in linea con de Groot et al. (b) Filtri pi\u00f9 severi su volume e trimestrali non aiutano oltre la "
    "soglia iniziale. (c) Gli short peggiorano il risultato a ogni dimensione: coerente con Stosik & Zaremba, il rendimento viene dalla gamba long.", "p"))

# --- 8. Risultati ---
st.append(P("8. Risultati", "h1"))
st.append(P("8.1 Le quattro varianti, periodo totale (2016\u2192oggi, netto dei costi)", "h2"))
righe = [["Variante", "Versione", "CAGR", "Volat.", "Sharpe", "Sortino", "Max DD", "Calmar", "Beta SPY"]]
for ver in ["senza_copertura", "con_copertura"]:
    for var in NOMI_VARIANTI:
        r = riga(ver, var, "totale")
        righe.append([NOMI_VARIANTI[var], NOMI_VERSIONI[ver], pct(r.cagr), pct(r.volatilita), num(r.sharpe),
                      num(r.sortino), pct(r.max_drawdown), num(r.calmar), num(r.beta_spy)])
righe.append(["SPY (buy & hold)", "\u2013", pct(spy_tot.cagr), pct(spy_tot.volatilita), num(spy_tot.sharpe),
              num(spy_tot.sortino), pct(spy_tot.max_drawdown), num(spy_tot.calmar), "1,00"])
st.append(tabella(righe, [3.6 * cm, 2.9 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.6 * cm, 1.6 * cm, 1.5 * cm, 1.5 * cm]))
st.append(P(
    "Senza copertura ogni miglioramento aggiunge valore: il confronto con il settore recupera la reversal (la variante generica \u00e8 quasi piatta), "
    "il filtro sul volume riduce il drawdown, quello sulle trimestrali migliora ancora lo Sharpe. Con la copertura il rendimento si abbassa perch\u00e9 "
    "si toglie la componente di mercato, ma le varianti mantengono lo stesso ordine.", "p"))
st.append(immagine("equity_varianti_vs_spy.png", 17))
st.append(P("Figura 1. Equity line delle 4 varianti contro SPY, base 100, netto dei costi. Il tratteggio segna l\u2019inizio dell\u2019out-of-sample.", "nota"))

st.append(P("8.2 Variante completa: in-sample contro out-of-sample", "h2"))
righe = [["Versione", "Periodo", "CAGR", "Volat.", "Sharpe", "Max DD", "Lordo annuo", "Costi annui", "Turnover", "Gross", "Beta"]]
nomi_per = {"totale": "Totale", "in_sample": "2016\u201321", "out_of_sample": "2022\u2192"}
for ver in ["senza_copertura", "con_copertura"]:
    for per in ["in_sample", "out_of_sample", "totale"]:
        r = riga(ver, "4_Completa", per)
        righe.append([NOMI_VERSIONI[ver], nomi_per[per], pct(r.cagr), pct(r.volatilita), num(r.sharpe), pct(r.max_drawdown),
                      pct(r.rendimento_lordo_annuo), pct(r.costi_annui), num(r.turnover_annuo, 1) + "\u00d7", pct(r.gross_medio, 0), num(r.beta_spy)])
for per in ["in_sample", "out_of_sample"]:
    r = riga("benchmark", "SPY", per)
    righe.append(["SPY", nomi_per[per], pct(r.cagr), pct(r.volatilita), num(r.sharpe), pct(r.max_drawdown), "\u2013", "\u2013", "\u2013", "\u2013", "1,00"])
st.append(tabella(righe, [2.5 * cm, 1.5 * cm, 1.3 * cm, 1.3 * cm, 1.3 * cm, 1.4 * cm, 1.7 * cm, 1.7 * cm, 1.7 * cm, 1.2 * cm, 1.2 * cm]))
st.append(P(
    f"Il \u201clordo/anno\u201d include il risultato della copertura; il turnover \u00e8 in multipli del capitale sulle sole azioni. "
    f"Dal 2022 lo Sharpe scende da {num(c_in.sharpe)} a {num(c_out.sharpe)} (senza copertura) e da {num(n_in.sharpe)} a {num(n_out.sharpe)} (con copertura): "
    "un calo atteso quando i parametri sono stati scelti sull\u2019in-sample. Il fondo resta positivo anche fuori campione, ma con rendimento modesto.", "p"))
st.append(KeepTogether([immagine("variante_completa_senza_copertura.png", 12.5),
                        P("Figura 2. Variante completa senza copertura: equity contro SPY, drawdown, gross e net exposure (media mobile a 20 giorni).", "nota")]))
st.append(KeepTogether([immagine("variante_completa_con_copertura.png", 12.5),
                        P("Figura 3. Variante completa con copertura SPY. \u201cNet dopo copertura\u201d \u00e8 il net in valore dopo la vendita di SPY; l\u2019esposizione al mercato (beta) \u00e8 circa zero.", "nota")]))

st.append(CondPageBreak(7 * cm))
st.append(P("8.3 Statistiche sui trade (variante completa, periodo totale)", "h2"))
tt = trade[(trade.variante == "4_Completa") & (trade.periodo == "totale")]
nomi_g = {"tutti": "Tutti", "lato_long": "Long", "lato_short": "Short", "uscita_take_profit": "Uscita: take profit",
          "uscita_stop_loss": "Uscita: stop loss", "uscita_time_stop": "Uscita: time stop", "uscita_aperta_a_fine": "Ancora aperti a fine periodo"}
righe = [["Gruppo", "N. trade", "Hit rate", "Rend. medio", "Durata media (giorni)", "P&L netto (contributo)"]]
for _, r in tt.iterrows():
    righe.append([nomi_g[r.gruppo], f"{int(r.n_trade)}", pct(r.hit_rate, 0) if r.n_trade else "\u2013",
                  pct(r.rendimento_medio_trade) if r.n_trade else "\u2013", num(r.durata_media_giorni, 1) if r.n_trade else "\u2013",
                  pct(r.pnl_netto_portafoglio)])
st.append(tabella(righe, [4.6 * cm, 2 * cm, 2 * cm, 2.4 * cm, 3 * cm, 3 * cm]))
st.append(P(
    "Hit rate e rendimento medio sono del titolo (con il segno del lato), prima dei costi; il P&L netto \u00e8 il contributo al portafoglio, dopo i costi. "
    "I take profit sono la parte che guadagna, i time stop e gli stop loss restituiscono una parte del guadagno. "
    "<b>Il numero di posizioni \u00e8 molto basso</b>: in media " + num(c_tot.n_long_medio, 1) + " long e " + num(c_tot.n_short_medio, 2) +
    " short aperte contemporaneamente. Gli short sono pochi e perdenti, quindi il fondo \u00e8 in pratica long-only con una piccola gamba short.", "nota"))

st.append(P("8.4 Sensibilit\u00e0 ai costi", "h2"))
st.append(P(
    "I 10 bps per lato sono un\u2019ipotesi prudente per large cap. Per mostrare quanto il risultato dipende da questa ipotesi, "
    "la variante completa \u00e8 stata rilanciata con costi diversi sulle sole azioni (parametri invariati):", "p"))
righe = [["Costo per lato", "Versione", "CAGR in-sample", "Sharpe in-sample", "CAGR out-of-sample", "Sharpe out-of-sample"]]
for bps in sorted(sens.costo_bps_per_lato.unique(), reverse=True):
    for ver in ["senza_copertura", "con_copertura"]:
        a = sens[(sens.costo_bps_per_lato == bps) & (sens.versione == ver) & (sens.periodo == "in_sample")].iloc[0]
        b = sens[(sens.costo_bps_per_lato == bps) & (sens.versione == ver) & (sens.periodo == "out_of_sample")].iloc[0]
        righe.append([f"{int(bps)} bps" + (" (base)" if bps == 10 else ""), NOMI_VERSIONI[ver], pct(a.cagr), num(a.sharpe), pct(b.cagr), num(b.sharpe)])
st.append(tabella(righe, [2.8 * cm, 3.2 * cm, 2.7 * cm, 2.7 * cm, 3 * cm, 2.6 * cm]))

# --- 9. Verifica ---
st.append(P("9. Verifica del P&L", "h1"))
st.append(P(
    "Prima di produrre le metriche, il codice ricostruisce il P&L giornaliero usando solo il log dei trade (data e prezzo di entrata e uscita, lato, peso) "
    "e lo confronta con quello calcolato dal motore di backtest, insieme ai costi, al turnover e al risultato della copertura. "
    "Se la differenza supera 10<super>\u221210</super> il programma si ferma con un errore. Su tutte le otto combinazioni (4 varianti \u00d7 2 versioni) "
    "la differenza massima \u00e8 dell\u2019ordine di 10<super>\u221216</super>."))

# --- 10. Limiti ---
st.append(P("10. Limiti", "h1"))
st += elenco([
    "<b>Survivorship bias:</b> si usano i costituenti di oggi dell\u2019S&P 500, quindi mancano i titoli usciti dall\u2019indice nel periodo; questo tende a migliorare i risultati.",
    "<b>Storico delle date delle trimestrali incompleto:</b> dove mancano si usa il proxy sul volume, meno preciso.",
    "<b>Costi semplificati:</b> 10 bps per lato senza market impact; i costi della copertura SPY (2 bps + 0,25% annuo) sono un\u2019ipotesi.",
    "<b>Confronto settoriale grossolano:</b> 11 settori GICS; un livello pi\u00f9 fine (industrie) sarebbe pi\u00f9 preciso ma ogni gruppo avrebbe pochi titoli.",
    "<b>Filtro di valutazione non incluso:</b> la traccia prevedeva un filtro su EV/EBITDA e P/B, ma yfinance fornisce solo multipli attuali, "
    "non uno storico affidabile e completo; applicarli a tutto il periodo avrebbe introdotto un look-ahead.",
    "<b>Selezione dei parametri:</b> circa 60 combinazioni provate sull\u2019in-sample; i risultati in-sample sono ottimistici. L\u2019out-of-sample 2022\u2192oggi \u00e8 stato guardato solo a scelte fatte.",
    "<b>Pochi trade e posizioni:</b> con le soglie finali il fondo ha in media 2\u20133 posizioni aperte e quasi nessuno short; la diversificazione \u00e8 bassa e un singolo titolo pu\u00f2 pesare fino al 12%.",
    "<b>Il rendimento non batte SPY</b> e fuori campione \u00e8 modesto: il progetto \u00e8 un esercizio metodologico, non una raccomandazione di investimento.",
])

# --- 11. Conclusioni ---
st.append(P("11. Conclusioni", "h1"))
st.append(P(
    "La short-term reversal sulle large cap USA, misurata rispetto al settore, produce un segnale reale ma piccolo, che i costi di negoziazione "
    "assorbono facilmente. I risultati confermano le indicazioni dei quattro paper: il confronto con il settore recupera la reversal che la versione "
    "generica non cattura; i filtri su volume e trimestrali riducono il rischio; il rendimento viene dalla gamba long; e il turnover \u00e8 il vero nemico. "
    f"Dopo aver ridotto i costi a circa {pct(c_tot.costi_annui)} l\u2019anno, la strategia senza copertura ha un CAGR di {pct(c_out.cagr)} fuori campione "
    f"e la versione market-neutral di {pct(n_out.cagr)}. Sono risultati modesti, ma onesti e riproducibili: tutto il codice, i dati e i passaggi sono nel repository."))

st.append(P("12. Riproducibilit\u00e0", "h1"))
st += elenco([
    f"Repository privato: <a href=\"{REPO_URL}\" color=\"#0b3d6b\">{REPO_URL}</a> (il README spiega come lanciare il codice dal Prompt dei comandi di Windows).",
    "<b>strategia.py</b>: tutti i parametri sono nel blocco di configurazione in cima; <i>python strategia.py --demo</i> verifica il codice su dati simulati.",
    "<b>output/</b>: confronto tra varianti, metriche in-sample/out-of-sample, rendimenti giornalieri (per il team Risk), log dei trade, sensibilit\u00e0 ai costi e grafici.",
    "<b>report/genera_report.py</b>: rigenera questo PDF leggendo i CSV, cos\u00ec le cifre non vengono ricopiate a mano.",
])

doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                        bottomMargin=2 * cm, title="Short-term reversal long/short su S&P 500",
                        author="Federico Amatruda", subject="UCFA Finance Society")
doc.build(st, onFirstPage=piede, onLaterPages=piede)
print("PDF creato:", PDF)
