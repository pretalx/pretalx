// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    const form = document.querySelector("#dialog-live form")
    const toggle = document.querySelector(".live-toggle")
    if (!form || !toggle) return
    form.addEventListener("submit", () => {
        toggle.disabled = true
    })
})
