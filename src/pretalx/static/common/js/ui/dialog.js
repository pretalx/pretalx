// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* Minimal enhancement to native modals, by making them close when the user clicks outside the dialog. */

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
        element.addEventListener("click", (ev) => {
            if (ev.target === element) {
                element.close()
            }
        })
    })
}

onReady(() => setupModals(document))
