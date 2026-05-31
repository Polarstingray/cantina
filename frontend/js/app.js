/*
 * app.js — wires the page to the backend.
 *   loadAll() pulls catalog + inventory + menu in parallel and re-renders.
 *   render* functions paint the DOM. on* handlers mutate then loadAll().
 */

import * as api from "./api.js";

const state = {
    foods: [],
    meals: [],
    inventory: { foods: {}, meals: {} },
    menu: {},
};

// --- helpers ---------------------------------------------------------------

const $ = (id) => document.getElementById(id);

function setStatus(msg, kind = "error") {
    const el = $("status");
    if (!msg) { el.hidden = true; el.textContent = ""; return; }
    el.hidden = false;
    el.textContent = msg;
    el.className = "status" + (kind === "info" ? " info" : "");
}

function el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
        if (k === "class") node.className = v;
        else if (k === "dataset") Object.assign(node.dataset, v);
        else if (k.startsWith("on") && typeof v === "function") {
            node.addEventListener(k.slice(2).toLowerCase(), v);
        }
        else if (k in node) node[k] = v;
        else node.setAttribute(k, v);
    }
    for (const child of [].concat(children)) {
        if (!child) continue;                  // skip null/undefined/false/0/""
        node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
}

function mealCost(meal) {
    let total = 0;
    for (const [name, amount] of Object.entries(meal.foods)) {
        const f = state.foods.find((x) => x.name === name);
        if (f) total += parseFloat(f.cost) * amount;
    }
    return total;
}

// --- render ----------------------------------------------------------------

function renderFoods(foods) {
    const container = $("foods");
    container.innerHTML = "";
    if (!foods.length) {
        container.appendChild(el("div", { class: "empty", textContent: "No foods yet." }));
        return;
    }
    for (const f of foods) {
        const macros = f.macros || ["0","0","0","0"];
        const stores = (f.stores || []).flatMap((s) => s.split(",")).map((s) => s.trim()).filter(Boolean);
        container.appendChild(el("div", { class: "card" }, [
            el("div", { class: "card-head" }, [
                el("div", { class: "name", textContent: f.name }),
                el("button", { class: "icon ghost danger-text", title: "delete", textContent: "×",
                    onclick: () => onDeleteFood(f.name) }),
            ]),
            f.desc && el("div", { class: "desc", textContent: f.desc }),
            el("div", { class: "cost", textContent: `$${parseFloat(f.cost).toFixed(2)}` }),
            el("div", { class: "macros",
                textContent: `${macros[0]} kcal • ${macros[1]}g carbs • ${macros[2]}g protein • ${macros[3]}g fat` }),
            stores.length && el("div", { class: "stores" },
                stores.map((s) => el("span", { class: "chip", textContent: s }))),
        ]));
    }
}

function renderMeals(meals) {
    const container = $("meals");
    container.innerHTML = "";
    if (!meals.length) {
        container.appendChild(el("div", { class: "empty", textContent: "No meals yet." }));
        return;
    }
    const foodNames = new Set(state.foods.map((f) => f.name));
    for (const m of meals) {
        const items = Object.entries(m.foods || {});
        const missing = items.map(([n]) => n).filter((n) => !foodNames.has(n));
        container.appendChild(el("div", { class: "card" }, [
            el("div", { class: "card-head" }, [
                el("div", { class: "name", textContent: m.name }),
                el("button", { class: "icon ghost danger-text", title: "delete", textContent: "×",
                    onclick: () => onDeleteMeal(m.name) }),
            ]),
            m.desc && el("div", { class: "desc", textContent: m.desc }),
            el("div", { class: "cost", textContent: `$${mealCost(m).toFixed(2)}` }),
            el("ul", { class: "ingredients-list" },
                items.map(([name, n]) => el("li", {
                    textContent: `${name} × ${n}${foodNames.has(name) ? "" : "  (missing)"}`,
                    class: foodNames.has(name) ? "" : "missing",
                }))),
            missing.length && el("div", { class: "warn-chip",
                textContent: `missing food${missing.length > 1 ? "s" : ""}: ${missing.join(", ")}` }),
        ]));
    }
}

function inventoryRow(name, qty, kind) {
    return el("div", { class: "inv-row" }, [
        el("span", { class: "label", textContent: name }),
        el("div", { class: "controls" }, [
            el("button", { class: "icon ghost", textContent: "−",
                onclick: () => onChangeStock(name, kind, -1) }),
            el("span", { class: "qty", textContent: String(qty) }),
            el("button", { class: "icon ghost", textContent: "+",
                onclick: () => onChangeStock(name, kind, +1) }),
        ]),
    ]);
}

function renderInventory(inv) {
    const container = $("inventory");
    container.innerHTML = "";

    const foodEntries = Object.entries(inv.foods || {});
    const mealEntries = Object.entries(inv.meals || {});

    const foodGroup = el("div", { class: "inv-group" }, [
        el("h3", { textContent: "Foods on hand" }),
    ]);
    if (!foodEntries.length) {
        foodGroup.appendChild(el("div", { class: "empty", textContent: "Nothing stocked." }));
    } else {
        for (const [name, qty] of foodEntries) foodGroup.appendChild(inventoryRow(name, qty, "food"));
    }
    container.appendChild(foodGroup);

    const mealGroup = el("div", { class: "inv-group" }, [
        el("h3", { textContent: "Prepared meals on hand" }),
    ]);
    if (!mealEntries.length) {
        mealGroup.appendChild(el("div", { class: "empty", textContent: "No prepared meals." }));
    } else {
        for (const [name, qty] of mealEntries) mealGroup.appendChild(inventoryRow(name, qty, "meal"));
    }
    container.appendChild(mealGroup);

    // refresh the stock-form dropdown
    refreshStockNameOptions();
}

function renderMenu(menu) {
    const container = $("menu");
    container.innerHTML = "";
    const entries = Object.entries(menu);
    if (!entries.length) {
        container.appendChild(el("div", { class: "empty", textContent: "No meals in the catalog yet." }));
        return;
    }
    for (const [name, count] of entries) {
        container.appendChild(el("div", { class: "menu-row" }, [
            el("span", { class: "label", textContent: name }),
            el("span", { class: "count" }, [
                document.createTextNode("can make "),
                el("strong", { textContent: String(count) }),
            ]),
            el("button", {
                textContent: "Make",
                disabled: count < 1,
                onclick: () => onMakeMeal(name),
            }),
        ]));
    }
}

// --- form handlers ---------------------------------------------------------

function readForm(form) {
    const fd = new FormData(form);
    const obj = {};
    for (const [k, v] of fd.entries()) obj[k] = v;
    return obj;
}

async function onAddFood(e) {
    e.preventDefault();
    const f = readForm(e.target);
    const body = {
        name: f.name.trim(),
        stores: f.stores ? f.stores.split(",").map((s) => s.trim()).filter(Boolean) : [],
        cost: parseFloat(f.cost) || 0,
        cals: parseInt(f.cals) || 0,
        carbs: parseFloat(f.carbs) || 0,
        protein: parseFloat(f.protein) || 0,
        fat: parseFloat(f.fat) || 0,
        desc: f.desc || "",
    };
    if (!body.name) return setStatus("Food needs a name.");
    try {
        await api.addFood(body);
        e.target.reset();
        e.target.hidden = true;
        setStatus(`Added food "${body.name}".`, "info");
        await loadAll();
    } catch (err) { setStatus(err.message); }
}

function addIngredientRow() {
    const rows = $("ingredient-rows");
    const select = el("select", { name: "food" },
        state.foods.map((f) => el("option", { value: f.name, textContent: f.name })));
    const amount = el("input", { type: "number", min: "1", value: "1", name: "amount" });
    const remove = el("button", { type: "button", class: "icon ghost", textContent: "×",
        onclick: () => row.remove() });
    const row = el("div", { class: "ingredient-row" }, [select, amount, remove]);
    rows.appendChild(row);
}

async function onAddMeal(e) {
    e.preventDefault();
    const form = e.target;
    const name = form.elements["name"].value.trim();
    const desc = form.elements["desc"].value;
    if (!name) return setStatus("Meal needs a name.");
    const ingredients = {};
    for (const row of $("ingredient-rows").querySelectorAll(".ingredient-row")) {
        const fname = row.querySelector("select").value;
        const amt = parseInt(row.querySelector("input").value) || 0;
        if (!fname || amt < 1) continue;
        ingredients[fname] = (ingredients[fname] || 0) + amt;
    }
    if (!Object.keys(ingredients).length) return setStatus("Meal needs at least one ingredient.");
    try {
        await api.addMeal({ name, foods: ingredients, desc });
        form.reset();
        $("ingredient-rows").innerHTML = "";
        form.hidden = true;
        setStatus(`Added meal "${name}".`, "info");
        await loadAll();
    } catch (err) { setStatus(err.message); }
}

async function onChangeStock(name, kind, delta) {
    try {
        if (delta > 0) await api.addStock({ name, amount: delta, kind });
        else await api.removeStock({ name, amount: -delta, kind });
        setStatus("");
        await loadAll();
    } catch (err) { setStatus(err.message); }
}

async function onAddStock(e) {
    e.preventDefault();
    const f = readForm(e.target);
    const amount = parseInt(f.amount) || 0;
    if (!f.name) return setStatus("Pick an item to stock.");
    if (amount < 1) return setStatus("Amount must be at least 1.");
    try {
        await api.addStock({ name: f.name, amount, kind: f.kind });
        setStatus(`Added ${amount} × ${f.name}.`, "info");
        await loadAll();
    } catch (err) { setStatus(err.message); }
}

async function onDeleteFood(name) {
    if (!confirm(`Delete food "${name}"? This also clears it from inventory.`)) return;
    try {
        await api.deleteFood(name);
        setStatus(`Deleted food "${name}".`, "info");
        await loadAll();
    } catch (err) { setStatus(err.message); }
}

async function onDeleteMeal(name) {
    if (!confirm(`Delete meal "${name}"? Any prepared stock is cleared too.`)) return;
    try {
        await api.deleteMeal(name);
        setStatus(`Deleted meal "${name}".`, "info");
        await loadAll();
    } catch (err) { setStatus(err.message); }
}

async function onMakeMeal(name) {
    try {
        await api.makeMeal(name);
        setStatus(`Made "${name}".`, "info");
        await loadAll();
    } catch (err) { setStatus(err.message); }
}

// keep the stock-form's item dropdown in sync with current catalog + kind
function refreshStockNameOptions() {
    const kindSel = document.querySelector('#add-stock-form select[name="kind"]');
    const nameSel = $("stock-name");
    if (!kindSel || !nameSel) return;
    const kind = kindSel.value;
    const source = kind === "meal" ? state.meals : state.foods;
    const prev = nameSel.value;
    nameSel.innerHTML = "";
    for (const item of source) {
        nameSel.appendChild(el("option", { value: item.name, textContent: item.name }));
    }
    if ([...nameSel.options].some((o) => o.value === prev)) nameSel.value = prev;
}

// --- bootstrap -------------------------------------------------------------

async function loadAll() {
    let foods, meals, inventory, menu;
    try {
        [foods, meals, inventory, menu] = await Promise.all([
            api.listFoods(), api.listMeals(), api.getInventory(), api.getMenu(),
        ]);
    } catch (err) {
        setStatus(`Could not reach the backend: ${err.message}. Is uvicorn running?`);
        return;
    }
    state.foods = foods;
    state.meals = meals;
    state.inventory = inventory;
    state.menu = menu;
    // Run each render independently so one buggy render doesn't blank the others.
    for (const [fn, data, name] of [
        [renderFoods, foods, "foods"], [renderMeals, meals, "meals"],
        [renderInventory, inventory, "inventory"], [renderMenu, menu, "menu"],
    ]) {
        try { fn(data); }
        catch (err) {
            console.error(`render ${name} failed:`, err);
            setStatus(`render ${name} failed: ${err.message}`);
        }
    }
}

function wireUi() {
    // collapsible forms
    for (const btn of document.querySelectorAll("button.toggle")) {
        btn.addEventListener("click", () => {
            const target = $(btn.dataset.target);
            if (target) target.hidden = !target.hidden;
        });
    }
    // cancel buttons: reset the form (including dynamic ingredient rows) and hide it.
    for (const btn of document.querySelectorAll("button.cancel")) {
        btn.addEventListener("click", () => {
            const target = $(btn.dataset.target);
            if (!target) return;
            if (typeof target.reset === "function") target.reset();
            const rows = target.querySelector("#ingredient-rows");
            if (rows) rows.innerHTML = "";
            target.hidden = true;
            setStatus("");
        });
    }
    $("add-food-form").addEventListener("submit", onAddFood);
    $("add-meal-form").addEventListener("submit", onAddMeal);
    $("add-stock-form").addEventListener("submit", onAddStock);
    $("add-ingredient").addEventListener("click", addIngredientRow);
    document.querySelector('#add-stock-form select[name="kind"]')
        .addEventListener("change", refreshStockNameOptions);
}

document.addEventListener("DOMContentLoaded", () => {
    wireUi();
    loadAll();
});
