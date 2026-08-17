// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* Minimal enhancement to native modals: wire up `[data-dialog-target]` openers and
 * `button.close-dialog` closers, and — for browsers without `closedby="any"` support —
 * add click-outside-to-close. Once Safari ships `closedby`, the fallback block can go.
 * See https://caniuse.com/?search=closedby, TODO 2027: check if we can drop this. */

const supportsClosedBy = "closedBy" in HTMLDialogElement.prototype

const dialogPrimaryAction = (dialog) => {
    const footer = dialog.querySelector(".dialog-footer")
    if (!footer) return null
    const buttons = Array.from(footer.querySelectorAll("button"))
    buttons.reverse()
    return buttons.find(
        (button) =>
            !button.classList.contains("close-dialog") &&
            !button.classList.contains("dialog-cancel") &&
            !button.classList.contains("btn-secondary"),
    )
}

const setupDialogEnter = (dialog) => {
    dialog.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter" || ev.shiftKey || ev.ctrlKey || ev.metaKey || ev.altKey) return
        const target = ev.target
        if (!target.matches?.("input:not([type=checkbox], [type=radio], [type=button], [type=submit], .choices__input)")) return
        const action = dialogPrimaryAction(dialog)
        if (!action) return
        ev.preventDefault()
        action.click()
    })
}

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
        setupDialogEnter(element)
        if (!supportsClosedBy) {
            element.addEventListener("click", (ev) => {
                if (ev.target === element) {
                    element.close()
                }
            })
        }
        // Upgrade server-rendered `<dialog open>` to a modal so it gets a backdrop and focus trap.
        if (element.open) {
            element.close()
            element.showModal()
        }
    })
}

document.addEventListener("click", (ev) => {
    const button = ev.target.closest?.("button.close-dialog")
    if (button) button.closest("dialog")?.close()
})

onReady(() => setupModals(document))
