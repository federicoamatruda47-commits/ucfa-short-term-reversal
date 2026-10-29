# Short-term reversal long/short su S&P 500 (UCFA Finance Society)

Backtest di una strategia di short-term reversal sul mercato USA, misurata con bande VWAP rolling
relative al settore GICS e confermata da un RSI di Wilder calcolato sulla serie z_rel.
Progetto di esercitazione, Università Cattolica di Milano.

## Come si lancia (Windows, Prompt dei comandi)

```bash
pip install -r requirements.txt
python strategia.py --demo
python strategia.py
```

- `--demo` usa dati simulati: serve solo a verificare che il codice giri, non scarica nulla.
- Senza `--demo` scarica i dati reali (yfinance, lista S&P 500 da Wikipedia). Il primo lancio richiede
  alcuni minuti; i dati vanno in `cache/` e dai lanci successivi non vengono riscaricati.
  Per riscaricare tutto, cancella la cartella `cache/`.

Tutti i parametri sono nel blocco di configurazione in cima a `strategia.py`, ciascuno commentato.

## Cosa fa la strategia

1. **Segnale**: distanza del prezzo dal VWAP a 20 giorni in deviazioni standard pesate per volume (z),
   meno la mediana di z del settore GICS lo stesso giorno (z_rel).
2. **Conferma**: RSI a 14 periodi calcolato su z_rel. Long se z_rel <= -1 e RSI < 25; short se z_rel >= +1 e RSI > 75.
3. **Filtri**: nessuna entrata con volume anomalo (top 10% dell'universo) o con trimestrale negli ultimi 5 giorni
   (proxy sul volume dove le date mancano).
4. **Uscite**: take profit quando z_rel torna a 0 (dopo almeno 3 giorni), stop a 1,5 deviazioni dall'entrata,
   time stop a 15 giorni.
5. **Sizing**: peso = 8% / volatilità annualizzata, massimo 12% per titolo, gross massimo 150%, short al massimo 10%.
6. **Esecuzione**: segnale alla chiusura del giorno d, trade all'apertura di d+1. Costi: 10 bps per lato sulle azioni,
   0,5% annuo di prestito sugli short.
7. **Due versioni**: senza copertura (long-biased) e con copertura del beta vendendo l'ETF SPY
   (2 bps per lato, 0,25% annuo di prestito, ipotesi dichiarate).

Le 4 varianti aggiungono un miglioramento alla volta: 1 generica, 2 + settore, 3 + volume, 4 + trimestrali (completa).

## Output (cartella `output/`)

| File | Contenuto |
|---|---|
| `confronto_varianti.csv` | Metriche delle 4 varianti nelle 2 versioni, con SPY |
| `metriche_in_out_sample.csv` | Stesse metriche per periodo: totale, in-sample (2016-2021), out-of-sample (2022+) |
| `rendimenti_giornalieri.csv` | Rendimenti giornalieri netti di tutte le serie (per il team Risk) |
| `dettaglio_giornaliero_*.csv` | Gross, net, copertura e costi giorno per giorno della variante completa |
| `log_trade.csv`, `statistiche_trade.csv` | Log di tutti i trade e statistiche per lato e motivo di uscita |
| `sensibilita_costi.csv` | Variante completa con costi di 10, 5, 3, 2 bps per lato |
| `*.png` | Equity delle varianti contro SPY; equity, drawdown ed esposizioni della variante completa |

I CSV usano `;` come separatore e `,` come decimale (si cambia con `CSV_SEP` e `CSV_DECIMALE`).

## Verifica

Prima di produrre le metriche, il codice ricostruisce il P&L giornaliero dal solo log dei trade e lo confronta
con quello del motore di backtest; se non coincidono, si ferma con un errore.

## Limiti da dichiarare

- **Survivorship bias**: si usano i costituenti attuali dell'S&P 500.
- **Storico delle trimestrali incompleto**: dove mancano le date si usa un proxy sul volume.
- **Costi semplificati**, senza market impact; i costi della copertura SPY sono un'ipotesi.
- **Confronto settoriale grossolano**: 11 settori GICS.
- **Filtro multipli non incluso**: yfinance fornisce solo multipli attuali, non uno storico affidabile.
- **Parametri scelti sull'in-sample** (circa 60 combinazioni provate): il risultato in-sample è in parte frutto della selezione.
  Il periodo out-of-sample (2022+) è stato guardato solo a scelte fatte.

## Supporto accademico

- Stosik & Zaremba (2026, Economics Letters), "Short-term reversal persists globally - If properly measured".
- Blitz, van der Grient & Honarvar (2023, SSRN), "Reversing the Trend of Short-Term Reversal".
- Medhat & Schmeling (2022, Review of Financial Studies), "Short-term Momentum".
- de Groot, Huij & Zhou (2012, Journal of Banking & Finance), "Another look at trading costs and short-term reversal profits".
