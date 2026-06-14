# Pearle – CJ Affiliate Serverside Conversietracking

## Principe

```
Bevestigingspagina (browser)
        │
        │  1. GA4 purchase event in dataLayer
        ▼
 vorige week)
        │
        ▼
conversion-client.html (via GTM geplaatst op bevestigingspagina)
        │
        │  1. cje cookie uitlezen (al eerder geplaatst via GTM/server voor "client side opl." 
        │  2. POST /cj-conversion  (JSON: orderId, items, cjEvent, demo, …)
        │
        ▼
server.py  –  server op pearle.nl
        │
        │  createOrders GraphQL mutation
        │  Authorization: Bearer <token>
        │
        ▼
tracking.api.cj.com/graphql  (CJ Affiliate API)
```

### Verschil met de oude Awin-opzet

Bij Awin werden conversies tijdelijk vastgehouden en afhankelijk van bepaalde voorwaarden doorgestuurd. Met CJ kunnen conversies **direct** server-side worden doorgeschoten .

De `cje` cookie (met de CJ click ID) wordt **niet** door dit script gezet — dat hebben we met behulp van jullie vorige week al ingeregeld via de /appt-tracker/visit hit . Sicco's html tag in GTM leest waarde cookie en order uit en schiet die door.  
  
De hele onderstaande opzet dient alleen als voorbeeld. Jullie zijn verder vrij om de server side kant in te richten zoals je wilt.

---

## Bestanden


| Bestand                  | Doel                                                                                                                                          |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `conversion-client.html` | Client-side script (plaatsen via GTM) door Sicco. Leest de GA4 dataLayer en de `cje` cookie en POST de orderdata naar de Pearle server.       |
| `server.py`              | Flask server. Ontvangt de POST van de client, kiest op basis van `demo` de test- of productie-API van CJ, en stuurt de GraphQL mutation door. |
| `cj_conversion.py`       | Business logic. Bouwt de GraphQL mutation en verstuurt hem naar CJ. Laadt credentials uit `.env`.                                             |
| `.env`                   | Geheime configuratie (niet in git). Bevat `CJ_ENTERPRISE_ID`, `CJ_ACTION_TRACKER_ID` en `CJ_ACCESS_TOKEN`. Zal Sicco afzonderlijk delen.      |
| `requirements.txt`       | Python dependencies (`flask`, `flask-cors`, `python-dotenv`, `requests`).                                                                     |


---

## Configuratie

Maak een `.env` bestand aan in de projectroot (zie `.env.example`):

```ini
CJ_ENTERPRISE_ID=jouw-enterprise-id
CJ_ACTION_TRACKER_ID=jouw-action-tracker-id
CJ_ACCESS_TOKEN=jouw-personal-access-token
# CJ_ENDPOINT=https://tracking.api.cj.com/graphql   # uncomment voor productie
```

De default endpoint is de **testomgeving** (`graphqltest`). Voor productie zet je
`CJ_ENDPOINT` expliciet op de live URL, of stuur je `demo: false` mee vanuit de client.

---

## Lokaal testen

**1. Installeer dependencies (eenmalig)**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Start de server**

```bash
python server.py
```

Server draait op `http://localhost:8080`.

**3. Open de testpagina**

```
http://localhost:8080/test
```

De pagina bevat een dummy GA4 dataLayer met twee Ray-Ban brillen en een dummy
`cje` cookie. Open de browser DevTools (F12 → Console + Network) en refresh de pagina.

- Console toont `[CJ demo] Conversie succesvol verstuurd.` en de volledige CJ-response
- Network toont de POST naar `/cj-conversion` en de teruggestuurde GraphQL response

**4. Health check**

```bash
curl http://localhost:8080/
```

**5. Handmatige POST (optioneel)**

```bash
curl -X POST http://localhost:8080/cj-conversion \
  -H "Content-Type: application/json" \
  -d '{
    "affiliateName": "CJ",
    "demo": true,
    "orderId":   "ORD-TEST-001",
    "eventTime": "2026-06-14T13:00:00.000Z",
    "amount":    379.90,
    "currency":  "EUR",
    "cjEvent":   "7166ddf3b35b11eb834200a10a1eb972",
    "coupon":    "ZOMER10",
    "discount":  20.00,
    "items": [
      {"sku": "RB3025-001/58", "unitPrice": 199.95, "quantity": 1, "discount": 10.00},
      {"sku": "RB2140-901",    "unitPrice": 179.95, "quantity": 1, "discount": 10.00}
    ]
  }'
```

---

## Demo vs. productie

Het veld `demo` in de clientpayload bepaalt welke CJ-endpoint de server gebruikt:


| `demo`  | Endpoint                                  |
| ------- | ----------------------------------------- |
| `true`  | `https://tracking.api.cj.com/graphqltest` |
| `false` | `https://tracking.api.cj.com/graphql`     |


Voor livegang: verander in `conversion-client.html` de regel `var demo = true;` naar `var demo = false;`.

---

## GTM-implementatie

1. Maak een **Custom HTML tag** aan in GTM
2. Plak de inhoud van `conversion-client.html` (zonder het dummy dataLayer blok bovenaan)
3. Stel als trigger in: **Purchase** (GA4 event) op de orderbevestigingspagina
4. Zorg dat de CJ click ID wordt opgeslagen als first-party cookie met naam `cje`
  (dit wordt doorgaans via een aparte GTM tag geregeld)

