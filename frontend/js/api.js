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

// Tiny fetch wrapper: builds the URL, sends JSON, parses JSON, throws on !ok.
async function request(path, options = {}) {
    const res = await fetch(BASE_URL + path, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    if (!res.ok) {
        // Backend sends { detail: "..." } on HTTPException; surface it.
        let detail = res.statusText;
        try { detail = (await res.json()).detail ?? detail; } catch { /* no body */ }
        throw new Error(`${res.status}: ${detail}`);
    }
    return res.json();
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
