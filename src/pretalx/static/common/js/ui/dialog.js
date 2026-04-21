// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* Minimal enhancement to native modals: wire up `[data-dialog-target]` openers and
 * `button.close-dialog` closers, and — for browsers without `closedby="any"` support —
 * add click-outside-to-close. Once Safari ships `closedby`, the fallback block can go.
 * See https://caniuse.com/?search=closedby, TODO 2027: check if we can drop this. */

const supportsClosedBy = "closedBy" in HTMLDialogElement.prototype

const setupModals = (container) => {
    container.querySelectorAll("[data-dialog-target]").forEach((element) => {
        const outerDialogElement = container.querySelector(
            element.dataset.dialogTarget,
        )
        if (!outerDialogElement) return
        element.addEventListener("click", function (ev) {
            ev.preventDefault()
            outerDialogElement.showModal()
        })
    })
    container.querySelectorAll("dialog").forEach((element) => {
        element.querySelectorAll("button.close-dialog").forEach((btn) => btn.addEventListener("click", () => element.close()))
        if (supportsClosedBy) return
        element.addEventListener("click", (ev) => {
            if (ev.target === element) {
                element.close()
            }
        })
    })
}

onReady(() => setupModals(document))
