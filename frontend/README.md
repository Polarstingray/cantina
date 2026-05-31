# Cantina — Frontend

Plain HTML + CSS + ES-module JavaScript. No framework, no build step.
FastAPI serves these static files alongside the API, so there is **one
process** to run, **one origin** to talk to, and no CORS to configure.

## File layout

```
frontend/
├── index.html        one <section> per backend area (foods, meals, inventory, menu)
├── css/styles.css    simple LAN-app styling
└── js/
    ├── api.js        one function per HTTP endpoint in backend/src/api.py
    └── app.js        render + form handlers + bootstrap
```

| Frontend                 | Backend (`backend/src/`)            |
|--------------------------|-------------------------------------|
| `js/api.js`              | `api.py` (the FastAPI routes)       |
| `#foods`, `#meals`       | catalog — `grocery.py` + `foods.py` |
| `#inventory`             | `inventory.py`                      |
| `#menu`                  | `menu.py`                           |

### Endpoint → `api.js` function

| HTTP                          | `api.js`              | Purpose                                  |
|-------------------------------|-----------------------|------------------------------------------|
| `GET    /foods`               | `listFoods()`         | list catalog foods                       |
| `POST   /foods`               | `addFood(food)`       | add a food to the catalog                |
| `DELETE /foods/{name}`        | `deleteFood(name)`    | remove from catalog + drop inventory     |
| `GET    /meals`               | `listMeals()`         | list catalog meals                       |
| `POST   /meals`               | `addMeal(meal)`       | add a meal (foods referenced by name)    |
| `DELETE /meals/{name}`        | `deleteMeal(name)`    | remove from catalog + drop inventory     |
| `GET    /inventory`           | `getInventory()`      | `{foods:{...}, meals:{...}}` on hand      |
| `POST   /inventory/add`       | `addStock(stock)`     | add N of a food/meal                     |
| `POST   /inventory/remove`    | `removeStock(stock)`  | remove N (rejects if not enough on hand) |
| `GET    /menu`                | `getMenu()`           | `{meal: how many buildable}`             |
| `POST   /menu/make/{name}`    | `makeMeal(name)`      | the "cart": spend a meal's ingredients   |

`app.js` reads top-to-bottom: `loadAll()` calls the four getters in parallel
→ hands each result to a `render*` function → those paint the matching
`<div>`. Mutations (`on*` handlers) call an `api.*` mutator then re-run
`loadAll()`. Errors surface in the top `#status` banner.

## Running it

From `backend/src/`:
```
./venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000
```
Then visit `http://<host>:8000/` from any device on the LAN (use
`localhost` from the host, or the host's LAN IP from a phone).

For a deploy that survives reboots, see `backend/deploy/cantina.service`.
