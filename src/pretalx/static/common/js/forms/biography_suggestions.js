// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

document.addEventListener("change", (e) => {
    const select = e.target.closest(".biography-suggestion-select")
    if (!select) return
    const profileId = select.value
    if (!profileId) return
    const dataEl = document.getElementById("biography-data")
    if (!dataEl) return
    const biographies = JSON.parse(dataEl.textContent)
    const biography = biographies[profileId]
    if (!biography) return
    const textarea = select.closest("form").querySelector("textarea[name='biography']")
    if (textarea) {
        textarea.value = biography
        textarea.dispatchEvent(new Event("input"))
    }
})
