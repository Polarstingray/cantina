/*
 * api.js
 *   Thin client for the cantina backend (backend/src/api.py).
 *   One function per HTTP endpoint, grouped to mirror the backend modules:
 *       catalog   -> grocery.py / foods.py   (/foods, /meals)
 *       inventory -> inventory.py            (/inventory*)
 *       menu/cart -> menu.py                 (/menu*)
 *   This file is the "map" of the backend: read it top-to-bottom to see the
 *   whole API surface. Everything here is fully written; the gaps to fill out
 *   live in app.js (rendering) and index.html (forms).
 */

// FastAPI now serves this page itself, so requests go to the same origin --
// no CORS, no LAN-IP fiddling. Leave empty for production. Override (e.g.
// "http://localhost:8000") only if you're hacking on the frontend served
// from a different port.
const BASE_URL = "";

// Optional hook: app.js sets this so any 401 (expired/no session) flips the UI
// back to the login screen instead of just erroring in the status banner.
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

// Tiny fetch wrapper: builds the URL, sends JSON, parses JSON, throws on !ok.
// credentials:"same-origin" sends the session cookie (same origin as the API).
async function request(path, options = {}) {
    const res = await fetch(BASE_URL + path, {
        credentials: "same-origin",
        ...options,
        // X-Requested-With is the CSRF guard: the backend requires it on every
        // state-changing request. A cross-site page can't set a custom header
        // without a CORS grant, which we don't give.
        headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "cantina",
            ...(options.headers || {}),
        },
    });
    if (!res.ok) {
        // Backend sends { detail: "..." } on HTTPException; surface it.
        let detail = res.statusText;
        try { detail = (await res.json()).detail ?? detail; } catch { /* no body */ }
        if (res.status === 401 && onUnauthorized) onUnauthorized();
        const err = new Error(`${res.status}: ${detail}`);
        err.status = res.status;
        throw err;
    }
    return res.json();
}

// --- auth ------------------------------------------------------------------

// POST /auth/login -> {ok, user:{email, role}}  (sets the session cookie)
export function login(email, password) {
    return request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

// POST /auth/logout (clears the session cookie)
export function logout() {
    return request("/auth/logout", { method: "POST" });
}

// GET /auth/me -> {email, role, household_id}  (401 if not logged in)
export function me() {
    return request("/auth/me");
}

// GET /auth/users (admin) / POST /auth/users (admin) body: {email, password, role}
export function listUsers() {
    return request("/auth/users");
}
export function addUser(user) {
    return request("/auth/users", { method: "POST", body: JSON.stringify(user) });
}

// --- catalog: foods --------------------------------------------------------

// GET /foods -> [ {type:"food", name, stores, cost, macros, desc, pic}, ... ]
export function listFoods() {
    return request("/foods");
}

// POST /foods  body: {name, stores, cost, cals, carbs, protein, fat, desc}
export function addFood(food) {
    return request("/foods", { method: "POST", body: JSON.stringify(food) });
}

// DELETE /foods/{name} -- removes from catalog AND drops orphaned inventory.
export function deleteFood(name) {
    return request(`/foods/${encodeURIComponent(name)}`, { method: "DELETE" });
}

// --- catalog: meals --------------------------------------------------------

// GET /meals -> [ {type:"meal", name, foods:{foodName:amount}, desc, pic}, ... ]
export function listMeals() {
    return request("/meals");
}

// POST /meals  body: {name, foods:{foodName:amount}, desc}
// (backend rejects with 400 if a referenced food isn't in the catalog)
export function addMeal(meal) {
    return request("/meals", { method: "POST", body: JSON.stringify(meal) });
}

// DELETE /meals/{name} -- removes from catalog AND drops prepared-meal stock.
export function deleteMeal(name) {
    return request(`/meals/${encodeURIComponent(name)}`, { method: "DELETE" });
}

// --- inventory -------------------------------------------------------------

// GET /inventory -> { foods:{name:qty}, meals:{name:qty} }
export function getInventory() {
    return request("/inventory");
}

// POST /inventory/add  body: {name, amount, kind:"food"|"meal"}
export function addStock(stock) {
    return request("/inventory/add", { method: "POST", body: JSON.stringify(stock) });
}

// POST /inventory/remove  body: {name, amount, kind:"food"|"meal"}
// (400 if there isn't enough on hand)
export function removeStock(stock) {
    return request("/inventory/remove", { method: "POST", body: JSON.stringify(stock) });
}

// --- menu / cart -----------------------------------------------------------

// GET /menu -> { mealName: howManyCanBeBuiltFromFoodsOnHand }
export function getMenu() {
    return request("/menu");
}

// POST /menu/make/{mealName} -- the "cart" action: spend a meal's ingredient
// foods from inventory. 404 unknown meal, 400 if not enough ingredients.
export function makeMeal(mealName) {
    return request(`/menu/make/${encodeURIComponent(mealName)}`, { method: "POST" });
}

// PUT /foods/{name} body: same shape as POST /foods. Replaces the named food.
export function updateFood(food) {
    return request(`/foods/${encodeURIComponent(food.name)}`,
        { method: "PUT", body: JSON.stringify(food) });
}

// GET /catalog/uses/{name} -> ["meal name", ...] meals that reference this food
export function getFoodUses(name) {
    return request(`/catalog/uses/${encodeURIComponent(name)}`);
}

// GET /lookup/barcode/{code} -> FoodIn-shaped {name, brand, cals, ...}
// 404 if no product is found, 400 if the code isn't a digit string.
export function lookupBarcode(code) {
    return request(`/lookup/barcode/${encodeURIComponent(code)}`);
}

// --- grocery / shopping list ---------------------------------------------

// GET /list -> {name: amount}
export function getList() {
    return request("/list");
}

// POST /list/add  body: {name, amount}  (auto-stubs catalog if unknown name)
export function addToList(item) {
    return request("/list/add", { method: "POST", body: JSON.stringify(item) });
}

// POST /list/remove  body: {name, amount}  (400 if not enough listed)
export function removeFromList(item) {
    return request("/list/remove", { method: "POST", body: JSON.stringify(item) });
}

// POST /list/check  body: {name, to_inventory?}  -> {moved: n}
// Removes the full listed amount from the list, adds to_inventory (default
// = full amount, capped) to inventory.
export function checkOffList(body) {
    return request("/list/check", { method: "POST", body: JSON.stringify(body) });
}

// POST /list/clear
export function clearList() {
    return request("/list/clear", { method: "POST" });
}

// --- spending log --------------------------------------------------------

// GET /spending  -> [{id, ts, name, qty, unit_cost, total, source}, ...]
// Optional `since` ("YYYY-MM-DD" or ISO) filters out older entries.
export function getSpending(since) {
    const q = since ? `?since=${encodeURIComponent(since)}` : "";
    return request("/spending" + q);
}

// GET /spending/totals?bucket=week|month -> {"YYYY-Www": $$$, ...}
export function getSpendingTotals(bucket = "week") {
    return request(`/spending/totals?bucket=${encodeURIComponent(bucket)}`);
}

// POST /spending body: {name, qty, unit_cost, source?}
export function addSpending(body) {
    return request("/spending", { method: "POST", body: JSON.stringify(body) });
}

// DELETE /spending/{id}
export function deleteSpending(id) {
    return request(`/spending/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// Sugar calls for the explicit Purchase affordance in the check-off and
// stock-add flows: pre-stamp the spending source server-side.
export function logCheckoffPurchase(body) {
    return request("/spending/from-checkoff", { method: "POST", body: JSON.stringify(body) });
}
export function logStockPurchase(body) {
    return request("/spending/from-stock-add", { method: "POST", body: JSON.stringify(body) });
}
