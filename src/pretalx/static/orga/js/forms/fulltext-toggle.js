// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    const searchInput = document.querySelector("#id_q")
    const fulltextToggle = document.querySelector("#fulltext-toggle")
    if (!searchInput || !fulltextToggle) return

    const fulltextCheckbox = fulltextToggle.querySelector("input[type=checkbox]")

    const updateVisibility = () => {
        if (searchInput.value || (fulltextCheckbox && fulltextCheckbox.checked)) {
            fulltextToggle.classList.remove("d-none")
        } else {
            fulltextToggle.classList.add("d-none")
        }
    }

    searchInput.addEventListener("input", updateVisibility)
    updateVisibility()
})
