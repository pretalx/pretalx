// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// The copy-from-event field is swapped in by htmx whenever the organiser changes.
let focusWasInField = false

const focusable = (select) => select?.closest(".choices") || select

document.addEventListener("htmx:beforeSwap", (event) => {
    const target = event.detail.target
    if (target?.id !== "copy-from-event-field") return
    focusWasInField = target.contains(document.activeElement)
})

document.addEventListener("htmx:load", (event) => {
    const swapped = event.detail.elt
    if (swapped?.id !== "copy-from-event") return
    window.initEnhancedSelects?.(swapped)
    if (!focusWasInField) return
    focusWasInField = false
    const target =
        focusable(swapped.querySelector("select")) ||
        focusable(document.querySelector("#id_organiser-organiser"))
    target?.focus()
})
