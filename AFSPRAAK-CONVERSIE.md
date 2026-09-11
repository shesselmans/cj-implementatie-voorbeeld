# CJ Afspraak-conversie — voor de SST-developer

Dit document beschrijft de nieuwe bestanden voor de **afspraak-conversie** (naast
de bestaande **transactie-conversie**) en wat er nodig is om dit server-side
(SST) te verwerken. De voorbeeld GTM code in "appointment-concreet-pnl.html" zal ik als code in GTM plaatsen (alleen dan met door jou te bepalen endpoint). Dit document gaat dus puur over de payload die je
straks binnenkrijgt en hoe die verwerkt moet worden richting CJ.

---

## 1. Kern van het verschil met de transactie-conversie

De afspraak-conversie is een **lead-actie** (een geboekte afspraak), geen
verkoop. Qua opzet is het bijna identiek aan de bestaande transactieflow, met
een paar concrete verschillen:

| Aspect              | Transactie (bestaand)                          | Afspraak (nieuw)                          |
| ------------------- | ----------------------------------------------- | ------------------------------------------ |
| Enterprise ID        | `CJ_ENTERPRISE_ID`                              | **Zelfde** `CJ_ENTERPRISE_ID`             |
| Action Tracker ID    | `CJ_ACTION_TRACKER_ID` (uit `.env`)              | **Vast**: `515933`                        |
| `orderId`            | GA4 `transaction_id`                             | GTM-macro `{{boekingNummer}}`             |
| `amount`             | Werkelijk ordertotaal (excl. btw, na korting)    | **Vast**: `3.00` (altijd, geen berekening) |
| `currency`           | `EUR`                                            | `EUR`                                      |
| `items`              | Lijst met producten (sku, unitPrice, qty, disc.) | **Niet aanwezig** — geen productregels     |
| `coupon`             | Optioneel, uit `{{couponCode}}`                  | **Nooit aanwezig** — per definitie niet van toepassing voor deze conversie |
| `discount`           | Optioneel, orderniveau                           | **Niet aanwezig**                          |
| `cjEvent`            | Uit de `cje`-first-party cookie                  | Zelfde mechanisme, ongewijzigd             |
| `eventTime`          | `new Date().toISOString()` op moment van hit     | Zelfde mechanisme, ongewijzigd             |

Kortom: de payload die je straks binnenkrijgt is een **kale versie** van de
transactiepayload — geen `items`, geen `coupon`, geen `discount` — met een
vaste `amount` en een andere `orderId`-bron.

---

## 2. Payload die de nieuwe SST-endpoint moet accepteren

Dit is exact wat `appointment-concreet-pnl.html` straks (via GTM) gaat posten:

```json
{
  "orderId":   "<waarde van {{boekingNummer}}>",
  "eventTime": "2026-06-14T13:00:00.000Z",
  "amount":    3.00,
  "currency":  "EUR",
  "cjEvent":   "<waarde van de cje-cookie>",
  "demo":      false
}
```

Geen `items`, geen `coupon`, geen `discount` — die velden komen niet in de
payload voor en hoeven dus ook niet verwerkt te worden.

---

## 3. Wat er richting CJ moet worden verstuurd

De GraphQL `createOrders`-mutation blijft qua vorm gelijk aan de
transactieconversie, met als verschil dat het `items`-veld volledig wordt
weggelaten en de `actionTrackerId` de afspraak-tracker is:

```graphql
mutation {
  createOrders(newOrders: [{
    enterpriseId:    "<zelfde enterprise ID als transacties>"
    actionTrackerId: 515933
    eventTime:       "2026-06-14T13:00:00.000Z"
    orderId:         "AFS-12345"
    cjEvent:         "<cje-cookie waarde>"
    amount:          3.0
    currency:        "EUR"
  }]) {
    orders { submissionId orderReceivedTime }
    errors { message fields }
  }
}
```

Verder identiek aan de bestaande transactie-mutatie: zelfde endpoint-logica
(test vs. live op basis van `demo`), zelfde `Authorization: Bearer <token>`
header, zelfde manier van errors afhandelen (`errors`-array in de response
checken).

---

## 4. Referentie-implementatie in dit repo

Er is geen productie-server hier — dit repo dient als **voorbeeld/referentie**
die je 1-op-1 kan overzetten naar de bestaande SST-code op `appt.pearle.nl`.

| Bestand                              | Rol                                                                                     |
| ------------------------------------- | ---------------------------------------------------------------------------------------- |
| `cj_appointment_conversion.py`        | Referentie voor de business logic: bouwt de mutation zonder `items`, met `actionTrackerId 515933`. Zie `send_appointment_conversion()`. |
| `cj_conversion.py`                    | Ongewijzigde/gedeelde logica (mutation builder, GraphQL-serialisatie) — de afspraakvariant hergebruikt dit. |
| `server.py` → `POST /cj-appointment-conversion` | Referentie-endpoint die de payload uit §2 valideert en doorstuurt. Dit is **niet** het echte pad op `appt.pearle.nl` — dat pad is nog niet vastgesteld. |
| `appointment-concreet-pnl.html`       | De GTM Custom HTML tag-inhoud die Sicco later plaatst. Post naar het (nog te bepalen) productie-endpoint. **Niet jouw actie** — puur ter info, zodat je weet welke payload eraan komt. |
| `conversion-client-afspraak.html`     | Alleen voor lokaal testen tegen `server.py` (dummy dataLayer-event, geen GTM). Niet relevant voor productie. |

---

## 5. Aandachtspunten

- **`actionTrackerId` is vast `515933`** voor PNL (andere id's voor GON en PBE krijg je nog), niet configureerbaar per order — anders dan bij transacties waar dit uit env-config komt.
- **Endpoint-pad op `appt.pearle.nl` staat nog niet vast.** `appointment-concreet-pnl.html` gebruikt voorlopig `https://appt.pearle.nl/appt-tracker/cj-appointment-conversion` als placeholder (zelfde patroon als de bestaande transactietag). Spreek met Sicco af welk pad de nieuwe endpoint krijgt zodra die gebouwd is, en werk de `url`-regel in dat bestand bij.
- **Geen moeilijke logica om te bepalen of afspraak heeft plaatsgevonden.** In tegenstelling tot de AWIN-appointments vroeger wordt de appointment hier gewoon altijd direct afgevuurd. Dus er hoeft (in ieder geval voorlopig) GEEN rekening mee worden gehouden of de afspraak geannuleerd is / al heeft plaatsgevonden. Gewoon appointment hit naar CJ afvuren als de betreffende endpoint wordt aangeroepen.
