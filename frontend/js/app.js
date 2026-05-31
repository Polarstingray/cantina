/*
 * app.js — hash-routed SPA over the cantina backend.
 *
 *   loadAll() pulls catalog + inventory + menu + list in parallel into
 *   the shared `state`. The router shows one #view-* and calls its render.
 *   render* functions paint DOM; on* handlers mutate then loadAll().
 *
 *   Routes:
 *     #/                  dashboard (all four sections + add forms)
 *     #/food/<name>       food detail
 *     #/meal/<name>       meal detail
 *     #/list              grocery list (+ inventory peek)
 *     #/inventory         full inventory page
 */

import * as api from "./api.js";

const state = {
    foods: [],
    meals: [],
    inventory: { foods: {}, meals: {} },
    menu: {},
    list: {},
};

// ===========================================================================
// helpers
// ===========================================================================

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
        else if (k in node) {
            // Some DOM attributes (e.g. <input>.list) are read-only getters;
            // fall back to setAttribute if the property assignment throws.
            try { node[k] = v; } catch { node.setAttribute(k, v); }
        }
        else node.setAttribute(k, v);
    }
    for (const child of [].concat(children)) {
        if (!child) continue;
        node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
}

const foodByName = (name) => state.foods.find((f) => f.name === name);
const mealByName = (name) => state.meals.find((m) => m.name === name);

// Format a numeric quantity for display: trim trailing zeros so 2 renders
// as "2", 1.5 as "1.5", 0.25 as "0.25" — without floating-point cruft.
function fmtQty(n) {
    if (n == null || isNaN(n)) return "0";
    const v = Math.round(Number(n) * 1000) / 1000;     // kill 1e-12 residue
    return Number.isInteger(v) ? String(v) : v.toString();
}

function mealCost(meal) {
    let total = 0;
    for (const [name, amount] of Object.entries(meal.foods || {})) {
        const f = foodByName(name);
        if (f) total += parseFloat(f.cost) * amount;
    }
    return total;
}

function mealMacros(meal) {
    const out = { cals: 0, carbs: 0, protein: 0, fat: 0 };
    for (const [name, amount] of Object.entries(meal.foods || {})) {
        const f = foodByName(name);
        if (!f) continue;
        const m = f.macros || ["0","0","0","0"];
        out.cals    += parseInt(m[0]) * amount;
        out.carbs   += parseFloat(m[1]) * amount;
        out.protein += parseFloat(m[2]) * amount;
        out.fat     += parseFloat(m[3]) * amount;
    }
    return out;
}

const fmtMacros = (m) =>
    `${m[0]} kcal • ${m[1]}g carbs • ${m[2]}g protein • ${m[3]}g fat`;

// ===========================================================================
// DASHBOARD renders
// ===========================================================================

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
        const card = el("a", { class: "card card-link", href: `#/food/${encodeURIComponent(f.name)}` }, [
            el("div", { class: "card-head" }, [
                el("div", { class: "name", textContent: f.name }),
                el("button", { class: "icon ghost danger-text", title: "delete", textContent: "×",
                    onclick: (e) => { e.preventDefault(); e.stopPropagation(); onDeleteFood(f.name); } }),
            ]),
            f.desc && el("div", { class: "desc", textContent: f.desc }),
            el("div", { class: "cost", textContent: `$${parseFloat(f.cost).toFixed(2)}` }),
            el("div", { class: "macros", textContent: fmtMacros(macros) }),
            stores.length && el("div", { class: "stores" },
                stores.map((s) => el("span", { class: "chip", textContent: s }))),
        ]);
        container.appendChild(card);
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
        const card = el("a", { class: "card card-link", href: `#/meal/${encodeURIComponent(m.name)}` }, [
            el("div", { class: "card-head" }, [
                el("div", { class: "name", textContent: m.name }),
                el("button", { class: "icon ghost danger-text", title: "delete", textContent: "×",
                    onclick: (e) => { e.preventDefault(); e.stopPropagation(); onDeleteMeal(m.name); } }),
            ]),
            m.desc && el("div", { class: "desc", textContent: m.desc }),
            el("div", { class: "cost", textContent: `$${mealCost(m).toFixed(2)}` }),
            el("ul", { class: "ingredients-list" },
                items.map(([name, n]) => el("li", {
                    textContent: `${name} × ${fmtQty(n)}${foodNames.has(name) ? "" : "  (missing)"}`,
                    class: foodNames.has(name) ? "" : "missing",
                }))),
            missing.length && el("div", { class: "warn-chip",
                textContent: `missing food${missing.length > 1 ? "s" : ""}: ${missing.join(", ")}` }),
        ]);
        container.appendChild(card);
    }
}

function inventoryRow(name, qty, kind, opts = {}) {
    const nameNode = opts.link && kind === "food"
        ? el("a", { href: `#/food/${encodeURIComponent(name)}`, textContent: name })
        : el("span", { textContent: name });
    return el("div", { class: "inv-row" }, [
        nameNode,
        el("div", { class: "controls" }, [
            el("button", { class: "icon ghost", textContent: "−",
                onclick: () => onChangeStock(name, kind, -0.5) }),
            el("span", { class: "qty", textContent: fmtQty(qty) }),
            el("button", { class: "icon ghost", textContent: "+",
                onclick: () => onChangeStock(name, kind, +0.5) }),
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
        for (const [name, qty] of foodEntries) foodGroup.appendChild(inventoryRow(name, qty, "food", { link: true }));
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
}

function renderListDashboard(list) {
    // keep the dashboard add-list datalist in sync with the current catalog
    const dl = $("dashboard-list-food-options");
    if (dl) {
        dl.innerHTML = "";
        for (const f of state.foods) dl.appendChild(el("option", { value: f.name }));
    }

    const container = $("list");
    container.innerHTML = "";
    const entries = Object.entries(list);
    if (!entries.length) {
        container.appendChild(el("div", { class: "empty",
            textContent: "Nothing on the list. Use “+ add to list” above." }));
        return;
    }
    for (const [name, qty] of entries) {
        container.appendChild(el("div", { class: "inv-row" }, [
            el("a", { href: `#/food/${encodeURIComponent(name)}`, textContent: name }),
            el("div", { class: "controls" }, [
                el("button", { class: "icon ghost", textContent: "−",
                    onclick: () => onListChange(name, -0.5) }),
                el("span", { class: "qty", textContent: fmtQty(qty) }),
                el("button", { class: "icon ghost", textContent: "+",
                    onclick: () => onListChange(name, +0.5) }),
                el("button", { class: "icon check-btn", title: "check off (move all to inventory)",
                    textContent: "✓",
                    onclick: () => onCheckOff(name, qty) }),
            ]),
        ]));
    }
}

async function onAddListFromDashboard(e) {
    e.preventDefault();
    const f = readForm(e.target);
    const name = (f.name || "").trim();
    const amount = parseFloat(f.amount) || 1;
    if (!name || amount <= 0) return setStatus("Need a name and a positive amount.");
    try {
        await api.addToList({ name, amount });
        e.target.reset();
        e.target.hidden = true;
        setStatus(`Added ${amount} × ${name} to grocery list.`, "info");
        await loadAll();
    } catch (err) { setStatus(err.message); }
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
            el("a", { href: `#/meal/${encodeURIComponent(name)}`, textContent: name }),
            el("span", { class: "count" }, [
                document.createTextNode("can make "),
                el("strong", { textContent: String(count) }),
            ]),
            el("button", { textContent: "Make", disabled: count < 1,
                onclick: () => onMakeMeal(name) }),
        ]));
    }
}

// ===========================================================================
// DETAIL renders
// ===========================================================================

function backLink() {
    return el("a", { class: "back-link", href: "#/", textContent: "← Dashboard" });
}

function renderFoodDetail(name) {
    const view = $("view-food");
    view.innerHTML = "";
    const f = foodByName(name);
    if (!f) {
        view.appendChild(backLink());
        view.appendChild(el("div", { class: "empty", textContent: `No food named "${name}".` }));
        return;
    }

    const macros = f.macros || ["0","0","0","0"];
    const stores = (f.stores || []).flatMap((s) => s.split(",")).map((s) => s.trim()).filter(Boolean);
    const stock = (state.inventory.foods || {})[f.name] || 0;
    const listed = state.list[f.name] || 0;

    view.appendChild(backLink());

    view.appendChild(el("section", { class: "detail" }, [
        el("div", { class: "detail-head" }, [
            el("h2", { textContent: f.name }),
            el("button", { class: "ghost danger-text", textContent: "Delete",
                onclick: () => onDeleteFood(f.name) }),
        ]),
        f.desc && el("p", { class: "desc", textContent: f.desc }),
        el("div", { class: "stats" }, [
            el("div", {}, [el("span", { class: "muted", textContent: "Cost: " }),
                           el("strong", { textContent: `$${parseFloat(f.cost).toFixed(2)}` })]),
            el("div", {}, [el("span", { class: "muted", textContent: "Calories: " }),
                           el("strong", { textContent: String(macros[0]) })]),
            el("div", {}, [el("span", { class: "muted", textContent: "Carbs: " }),
                           el("strong", { textContent: `${macros[1]}g` })]),
            el("div", {}, [el("span", { class: "muted", textContent: "Protein: " }),
                           el("strong", { textContent: `${macros[2]}g` })]),
            el("div", {}, [el("span", { class: "muted", textContent: "Fat: " }),
                           el("strong", { textContent: `${macros[3]}g` })]),
        ]),
        stores.length && el("div", { class: "stores" },
            stores.map((s) => el("span", { class: "chip", textContent: s }))),
    ]));

    // stock controls
    view.appendChild(el("section", { class: "detail" }, [
        el("h3", { textContent: "Stock on hand" }),
        el("div", { class: "inv-row" }, [
            el("span", { textContent: `${fmtQty(stock)} in inventory` }),
            el("div", { class: "controls" }, [
                el("button", { class: "icon ghost", textContent: "−",
                    onclick: () => onChangeStock(f.name, "food", -0.5) }),
                el("span", { class: "qty", textContent: fmtQty(stock) }),
                el("button", { class: "icon ghost", textContent: "+",
                    onclick: () => onChangeStock(f.name, "food", +0.5) }),
            ]),
        ]),
    ]));

    // add to grocery list
    const addListForm = el("form", { class: "form inline-form",
        onsubmit: (e) => { e.preventDefault();
            const amt = parseFloat(e.target.elements.amount.value) || 1;
            onAddToList(f.name, amt); } }, [
        el("label", {}, [
            document.createTextNode("Add to grocery list "),
            el("input", { type: "number", name: "amount", min: "0.5", step: "0.5", value: "1" }),
        ]),
        el("button", { type: "submit", textContent: "Add" }),
        listed > 0 && el("span", { class: "muted", textContent: `(currently ${fmtQty(listed)} listed)` }),
    ]);
    view.appendChild(el("section", { class: "detail" }, [
        el("h3", { textContent: "Grocery list" }),
        addListForm,
    ]));

    // used in
    const usesContainer = el("div", {}, [el("span", { class: "muted", textContent: "loading…" })]);
    api.getFoodUses(f.name).then((uses) => {
        usesContainer.innerHTML = "";
        if (!uses.length) {
            usesContainer.appendChild(el("span", { class: "muted", textContent: "Not used in any meal." }));
            return;
        }
        for (const mealName of uses) {
            usesContainer.appendChild(el("a", { class: "chip-link",
                href: `#/meal/${encodeURIComponent(mealName)}`, textContent: mealName }));
        }
    }).catch((err) => { usesContainer.textContent = err.message; });
    view.appendChild(el("section", { class: "detail" }, [
        el("h3", { textContent: "Used in" }),
        usesContainer,
    ]));

    // edit form (prefilled)
    const editForm = el("form", { class: "form",
        onsubmit: (e) => { e.preventDefault(); onUpdateFood(e.target, f.name); } }, [
        el("div", { class: "form-grid" }, [
            el("label", {}, [document.createTextNode("Cost ($)"),
                el("input", { name: "cost", type: "number", step: "0.01", min: "0", value: String(f.cost) })]),
            el("label", {}, [document.createTextNode("Calories"),
                el("input", { name: "cals", type: "number", min: "0", value: String(macros[0]) })]),
            el("label", {}, [document.createTextNode("Carbs (g)"),
                el("input", { name: "carbs", type: "number", step: "0.1", min: "0", value: String(macros[1]) })]),
            el("label", {}, [document.createTextNode("Protein (g)"),
                el("input", { name: "protein", type: "number", step: "0.1", min: "0", value: String(macros[2]) })]),
            el("label", {}, [document.createTextNode("Fat (g)"),
                el("input", { name: "fat", type: "number", step: "0.1", min: "0", value: String(macros[3]) })]),
            el("label", { class: "wide" }, [document.createTextNode("Stores (comma separated)"),
                el("input", { name: "stores", value: stores.join(", ") })]),
            el("label", { class: "wide" }, [document.createTextNode("Description"),
                el("input", { name: "desc", value: f.desc || "" })]),
        ]),
        el("div", { class: "form-actions" }, [
            el("button", { type: "submit", textContent: "Save changes" }),
        ]),
    ]);
    view.appendChild(el("section", { class: "detail" }, [
        el("h3", { textContent: "Edit" }),
        editForm,
    ]));
}

function renderMealDetail(name) {
    const view = $("view-meal");
    view.innerHTML = "";
    const m = mealByName(name);
    if (!m) {
        view.appendChild(backLink());
        view.appendChild(el("div", { class: "empty", textContent: `No meal named "${name}".` }));
        return;
    }

    const items = Object.entries(m.foods || {});
    const foodNames = new Set(state.foods.map((f) => f.name));
    const macros = mealMacros(m);
    const buildable = state.menu[m.name] ?? 0;

    view.appendChild(backLink());

    view.appendChild(el("section", { class: "detail" }, [
        el("div", { class: "detail-head" }, [
            el("h2", { textContent: m.name }),
            el("button", { class: "ghost danger-text", textContent: "Delete",
                onclick: () => onDeleteMeal(m.name) }),
        ]),
        m.desc && el("p", { class: "desc", textContent: m.desc }),
        el("div", { class: "stats" }, [
            el("div", {}, [el("span", { class: "muted", textContent: "Total cost: " }),
                           el("strong", { textContent: `$${mealCost(m).toFixed(2)}` })]),
            el("div", {}, [el("span", { class: "muted", textContent: "Calories: " }),
                           el("strong", { textContent: String(macros.cals) })]),
            el("div", {}, [el("span", { class: "muted", textContent: "Carbs: " }),
                           el("strong", { textContent: `${macros.carbs.toFixed(1)}g` })]),
            el("div", {}, [el("span", { class: "muted", textContent: "Protein: " }),
                           el("strong", { textContent: `${macros.protein.toFixed(1)}g` })]),
            el("div", {}, [el("span", { class: "muted", textContent: "Fat: " }),
                           el("strong", { textContent: `${macros.fat.toFixed(1)}g` })]),
        ]),
    ]));

    view.appendChild(el("section", { class: "detail" }, [
        el("h3", { textContent: "Ingredients" }),
        el("ul", { class: "ingredients-list" },
            items.map(([n, qty]) => el("li", { class: foodNames.has(n) ? "" : "missing" }, [
                foodNames.has(n)
                    ? el("a", { href: `#/food/${encodeURIComponent(n)}`, textContent: n })
                    : el("span", { textContent: n }),
                document.createTextNode(` × ${fmtQty(qty)}${foodNames.has(n) ? "" : "  (missing from catalog)"}`),
            ]))),
    ]));

    view.appendChild(el("section", { class: "detail" }, [
        el("h3", { textContent: "Make it" }),
        el("div", { class: "menu-row" }, [
            el("span", {}, [document.createTextNode("can make "),
                el("strong", { textContent: String(buildable) })]),
            el("button", { textContent: "Make one", disabled: buildable < 1,
                onclick: () => onMakeMeal(m.name) }),
        ]),
    ]));
}

function renderListPage() {
    const view = $("view-list");
    view.innerHTML = "";
    view.appendChild(backLink());

    const entries = Object.entries(state.list);
    const invFoods = state.inventory.foods || {};

    // add-to-list form (datalist of catalog foods, plus free text)
    const dlId = "list-food-options";
    const datalist = el("datalist", { id: dlId },
        state.foods.map((f) => el("option", { value: f.name })));
    const addForm = el("form", { class: "form",
        onsubmit: (e) => {
            e.preventDefault();
            const name = e.target.elements.name.value.trim();
            const amount = parseFloat(e.target.elements.amount.value) || 1;
            if (!name || amount <= 0) return setStatus("Need a name and a positive amount.");
            onAddToList(name, amount);
            e.target.reset();
        } }, [
        datalist,
        el("div", { class: "form-grid" }, [
            el("label", { class: "wide" }, [document.createTextNode("Item"),
                el("input", { name: "name", required: true, list: dlId,
                    placeholder: "type or pick from catalog" })]),
            el("label", {}, [document.createTextNode("Amount"),
                el("input", { name: "amount", type: "number", min: "0.5", step: "0.5", value: "1" })]),
        ]),
        el("div", { class: "form-actions" }, [
            el("button", { type: "submit", textContent: "Add to list" }),
        ]),
    ]);

    const left = el("section", { class: "detail" }, [
        el("div", { class: "detail-head" }, [
            el("h2", { textContent: "Grocery list" }),
            entries.length > 0 && el("button", { class: "ghost danger-text", textContent: "Clear all",
                onclick: onClearList }),
        ]),
        addForm,
        entries.length === 0
            ? el("div", { class: "empty", textContent: "Nothing on the list." })
            : el("div", { class: "list-rows" }, entries.map(([name, qty]) => listRow(name, qty))),
    ]);

    // right column: inventory peek for items on the list
    const peekEntries = entries
        .map(([name]) => [name, invFoods[name] || 0]);
    const right = el("section", { class: "detail peek" }, [
        el("h3", { textContent: "Already in inventory" }),
        peekEntries.length === 0
            ? el("div", { class: "empty", textContent: "List is empty." })
            : el("div", { class: "list-rows" }, peekEntries.map(([name, qty]) =>
                el("div", { class: "inv-row" }, [
                    el("a", { href: `#/food/${encodeURIComponent(name)}`, textContent: name }),
                    el("span", { class: "qty",
                        textContent: qty > 0 ? `${qty} on hand` : "none on hand",
                        title: qty > 0 ? "already in inventory" : "" }),
                ]))),
    ]);

    view.appendChild(el("div", { class: "list-grid" }, [left, right]));
}

function listRow(name, qty) {
    // Default the "moved to inventory" amount to the full listed amount.
    const row = el("div", { class: "list-row" }, [
        el("a", { class: "list-name", href: `#/food/${encodeURIComponent(name)}`, textContent: name }),
        el("span", { class: "qty", textContent: fmtQty(qty) }),
        el("button", { class: "check-btn", textContent: "✓ check off",
            onclick: () => toggleCheckRow(row, name, qty) }),
    ]);
    return row;
}

function toggleCheckRow(row, name, qty) {
    const existing = row.querySelector(".check-form");
    if (existing) { existing.remove(); return; }
    const form = el("form", { class: "check-form",
        onsubmit: (e) => { e.preventDefault();
            const n = parseFloat(e.target.elements.n.value);
            onCheckOff(name, isNaN(n) ? qty : n); } }, [
        el("label", {}, [
            document.createTextNode("Move to inventory: "),
            el("input", { type: "number", name: "n", min: "0", step: "0.5",
                max: fmtQty(qty), value: fmtQty(qty) }),
            document.createTextNode(` of ${fmtQty(qty)}`),
        ]),
        el("button", { type: "submit", textContent: "Confirm" }),
        el("button", { type: "button", class: "ghost", textContent: "Cancel",
            onclick: () => form.remove() }),
    ]);
    row.appendChild(form);
}

function renderInventoryPage() {
    const view = $("view-inventory");
    view.innerHTML = "";
    view.appendChild(backLink());

    const inv = state.inventory;
    const foodEntries = Object.entries(inv.foods || {});
    const mealEntries = Object.entries(inv.meals || {});

    const stockForm = el("form", { class: "form",
        onsubmit: (e) => {
            e.preventDefault();
            const name = e.target.elements.name.value.trim();
            const amount = parseFloat(e.target.elements.amount.value) || 1;
            if (!name || amount <= 0) return setStatus("Need a name and a positive amount.");
            onStockAdd(name, amount);
            e.target.reset();
        } }, [
        el("div", { class: "form-grid" }, [
            el("label", { class: "wide" }, [document.createTextNode("Item (any name, will be added to catalog if new)"),
                el("input", { name: "name", required: true,
                    placeholder: "type a name" })]),
            el("label", {}, [document.createTextNode("Amount"),
                el("input", { name: "amount", type: "number", min: "0.5", step: "0.5", value: "1" })]),
        ]),
        el("div", { class: "form-actions" }, [
            el("button", { type: "submit", textContent: "Stock it" }),
        ]),
    ]);

    view.appendChild(el("section", { class: "detail" }, [
        el("h2", { textContent: "Inventory" }),
        el("h3", { textContent: "Stock a new item" }),
        stockForm,
    ]));

    view.appendChild(el("section", { class: "detail" }, [
        el("h3", { textContent: `Foods on hand (${foodEntries.length})` }),
        foodEntries.length === 0
            ? el("div", { class: "empty", textContent: "Nothing stocked." })
            : el("div", { class: "list-rows" },
                foodEntries.map(([name, qty]) => bulkInventoryRow(name, qty, "food"))),
    ]));

    view.appendChild(el("section", { class: "detail" }, [
        el("h3", { textContent: `Prepared meals on hand (${mealEntries.length})` }),
        mealEntries.length === 0
            ? el("div", { class: "empty", textContent: "No prepared meals." })
            : el("div", { class: "list-rows" },
                mealEntries.map(([name, qty]) => bulkInventoryRow(name, qty, "meal"))),
    ]));
}

function bulkInventoryRow(name, qty, kind) {
    const nameNode = kind === "food"
        ? el("a", { href: `#/food/${encodeURIComponent(name)}`, textContent: name })
        : el("a", { href: `#/meal/${encodeURIComponent(name)}`, textContent: name });

    let setInput;
    const setForm = el("form", { class: "inline-set",
        onsubmit: (e) => {
            e.preventDefault();
            const target = parseFloat(setInput.value);
            if (isNaN(target) || target < 0) return setStatus("Enter a non-negative number.");
            onSetStock(name, kind, qty, target);
        } }, [
        document.createTextNode("set to "),
        (setInput = el("input", { type: "number", min: "0", step: "0.5", value: fmtQty(qty) })),
        el("button", { type: "submit", textContent: "Set" }),
    ]);

    return el("div", { class: "inv-row" }, [
        nameNode,
        el("div", { class: "controls" }, [
            el("button", { class: "icon ghost", textContent: "−",
                onclick: () => onChangeStock(name, kind, -0.5) }),
            el("span", { class: "qty", textContent: fmtQty(qty) }),
            el("button", { class: "icon ghost", textContent: "+",
                onclick: () => onChangeStock(name, kind, +0.5) }),
            setForm,
        ]),
    ]);
}

// ===========================================================================
// form / action handlers
// ===========================================================================

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

async function onUpdateFood(form, name) {
    const f = readForm(form);
    const body = {
        name,
        stores: f.stores ? f.stores.split(",").map((s) => s.trim()).filter(Boolean) : [],
        cost: parseFloat(f.cost) || 0,
        cals: parseInt(f.cals) || 0,
        carbs: parseFloat(f.carbs) || 0,
        protein: parseFloat(f.protein) || 0,
        fat: parseFloat(f.fat) || 0,
        desc: f.desc || "",
    };
    try {
        await api.updateFood(body);
        setStatus(`Saved "${name}".`, "info");
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

function addIngredientRow() {
    const rows = $("ingredient-rows");
    const select = el("select", { name: "food" },
        state.foods.map((f) => el("option", { value: f.name, textContent: f.name })));
    const amount = el("input", { type: "number", min: "0.5", step: "0.5", value: "1", name: "amount" });
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
        const amt = parseFloat(row.querySelector("input").value) || 0;
        if (!fname || amt <= 0) continue;
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
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

async function onSetStock(name, kind, current, target) {
    const delta = target - current;
    if (delta === 0) return;
    try {
        if (delta > 0) await api.addStock({ name, amount: delta, kind });
        else await api.removeStock({ name, amount: -delta, kind });
        setStatus(`Set ${name} to ${target}.`, "info");
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

async function onStockAdd(name, amount) {
    try {
        await api.addStock({ name, amount, kind: "food" });
        setStatus(`Stocked ${amount} × ${name}.`, "info");
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

async function onDeleteFood(name) {
    if (!confirm(`Delete food "${name}"? This also clears it from inventory and the grocery list.`)) return;
    try {
        await api.deleteFood(name);
        setStatus(`Deleted food "${name}".`, "info");
        if (location.hash.startsWith(`#/food/`)) location.hash = "#/";
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

async function onDeleteMeal(name) {
    if (!confirm(`Delete meal "${name}"? Any prepared stock is cleared too.`)) return;
    try {
        await api.deleteMeal(name);
        setStatus(`Deleted meal "${name}".`, "info");
        if (location.hash.startsWith(`#/meal/`)) location.hash = "#/";
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

async function onMakeMeal(name) {
    try {
        await api.makeMeal(name);
        setStatus(`Made "${name}".`, "info");
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

async function onListChange(name, delta) {
    try {
        if (delta > 0) await api.addToList({ name, amount: delta });
        else await api.removeFromList({ name, amount: -delta });
        setStatus("");
        await loadAll();
    } catch (err) { setStatus(err.message); }
}

async function onAddToList(name, amount) {
    try {
        await api.addToList({ name, amount });
        setStatus(`Added ${amount} × ${name} to grocery list.`, "info");
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

async function onCheckOff(name, toInventory) {
    try {
        const res = await api.checkOffList({ name, to_inventory: toInventory });
        setStatus(`Checked off "${name}" (+${res.moved} to inventory).`, "info");
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

async function onClearList() {
    if (!confirm("Clear the entire grocery list?")) return;
    try {
        await api.clearList();
        setStatus("Cleared the grocery list.", "info");
        await loadAll();
        renderCurrentRoute();
    } catch (err) { setStatus(err.message); }
}

// ===========================================================================
// router
// ===========================================================================

const VIEWS = ["view-dashboard", "view-food", "view-meal", "view-list", "view-inventory"];

function parseRoute() {
    const hash = location.hash || "#/";
    const path = hash.startsWith("#") ? hash.slice(1) : hash;
    // "/food/apple" -> ["food", "apple"]
    const parts = path.split("/").filter(Boolean);
    return parts;
}

function showView(id) {
    for (const v of VIEWS) {
        const node = $(v);
        if (node) node.hidden = (v !== id);
    }
}

function setActiveNav(routeBase) {
    for (const a of document.querySelectorAll(".topnav a")) {
        a.classList.toggle("active", a.dataset.route === routeBase);
    }
}

function renderCurrentRoute() {
    const parts = parseRoute();

    if (parts.length === 0) {
        showView("view-dashboard");
        setActiveNav("/");
        renderFoods(state.foods);
        renderMeals(state.meals);
        renderInventory(state.inventory);
        renderListDashboard(state.list);
        renderMenu(state.menu);
        return;
    }
    if (parts[0] === "food" && parts[1]) {
        showView("view-food");
        setActiveNav("");
        renderFoodDetail(decodeURIComponent(parts[1]));
        return;
    }
    if (parts[0] === "meal" && parts[1]) {
        showView("view-meal");
        setActiveNav("");
        renderMealDetail(decodeURIComponent(parts[1]));
        return;
    }
    if (parts[0] === "list") {
        showView("view-list");
        setActiveNav("/list");
        renderListPage();
        return;
    }
    if (parts[0] === "inventory") {
        showView("view-inventory");
        setActiveNav("/inventory");
        renderInventoryPage();
        return;
    }
    // unknown route -> dashboard
    location.hash = "#/";
}

// ===========================================================================
// bootstrap
// ===========================================================================

async function loadAll() {
    let foods, meals, inventory, menu, list;
    try {
        [foods, meals, inventory, menu, list] = await Promise.all([
            api.listFoods(), api.listMeals(), api.getInventory(), api.getMenu(), api.getList(),
        ]);
    } catch (err) {
        setStatus(`Could not reach the backend: ${err.message}. Is uvicorn running?`);
        return;
    }
    state.foods = foods;
    state.meals = meals;
    state.inventory = inventory;
    state.menu = menu;
    state.list = list;
    renderCurrentRoute();
}

function wireDashboardForms() {
    for (const btn of document.querySelectorAll("button.toggle")) {
        btn.addEventListener("click", () => {
            const target = $(btn.dataset.target);
            if (target) target.hidden = !target.hidden;
        });
    }
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
    $("add-list-form").addEventListener("submit", onAddListFromDashboard);
    $("add-ingredient").addEventListener("click", addIngredientRow);
}

document.addEventListener("DOMContentLoaded", async () => {
    wireDashboardForms();
    window.addEventListener("hashchange", renderCurrentRoute);
    await loadAll();
    renderCurrentRoute();
});
