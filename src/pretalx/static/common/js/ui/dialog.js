// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* Minimal enhancement to native modals, by making them close when the user clicks outside the dialog. */

const setupModals = () => {
    document.querySelectorAll("[data-dialog-target]").forEach((element) => {
        const outerDialogElement = document.querySelector(
            element.dataset.dialogTarget,
        )
        if (!outerDialogElement) return
        element.addEventListener("click", function (ev) {
            ev.preventDefault()
            outerDialogElement.showModal()
        })
    })
    document.querySelectorAll("dialog").forEach((element) => {
        element.querySelectorAll("button.close-dialog").forEach((btn) => btn.addEventListener("click", () => element.close()))
        element.addEventListener("click", () => element.close())
        element.querySelector("div").addEventListener("click", (ev) => ev.stopPropagation())
    })
}

onReady(setupModals)
