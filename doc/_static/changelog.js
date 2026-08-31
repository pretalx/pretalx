// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("changelog-show-all")
    const link = toggle && toggle.querySelector(".changelog-show-all-link")
    if (!link) return
    link.addEventListener("click", (event) => {
        event.preventDefault()
        for (const item of toggle.closest("ul").querySelectorAll(".changelog-hidden")) {
            item.classList.remove("changelog-hidden")
        }
        toggle.remove()
    })
})
