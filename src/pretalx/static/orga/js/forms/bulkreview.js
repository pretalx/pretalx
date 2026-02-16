// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const resetSaveButton = (e) => {
    const row = e.target.closest("tr[id^='review-row-']")
    if (!row) return
    const btn = row.querySelector(".bulk-review-save")
    if (!btn) return
    btn.disabled = false
    btn.classList.remove("btn-outline-success", "btn-danger")
    btn.classList.add("btn-success")
}

const table = document.querySelector(".bulk-review-table")
if (table) {
    table.addEventListener("input", resetSaveButton)
    table.addEventListener("change", resetSaveButton)

    document.addEventListener("htmx:configRequest", (e) => {
        e.detail.headers["X-CSRFToken"] = getCookie("pretalx_csrftoken")
    })

    document.addEventListener("htmx:beforeRequest", (e) => {
        const btn = e.detail.elt
        if (!btn.classList.contains("bulk-review-save")) return
        btn.querySelector(".bulk-review-icon").classList.add("d-none")
        btn.querySelector(".bulk-review-loading").classList.remove("d-none")
    })
}
