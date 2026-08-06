// SPDX-FileCopyrightText: 2023-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* These functions are used in the email editor, in order to insert clicked
 * placeholders into the currently focused input field. */

let lastFocusedInput = null

const makePlaceholderActive = (placeholder) => {
    if (!placeholder) return
    placeholder.querySelector(".unavailable").classList.add("d-none")
    placeholder.querySelector(".list-group").classList.remove("d-none")
}

const makePlaceholderInactive = (placeholder) => {
    if (!placeholder) return
    placeholder.querySelector(".unavailable").classList.remove("d-none")
    placeholder.querySelector(".list-group").classList.add("d-none")
}

const updateVisiblePlaceholders = (speakersField) => {
    const note = document.querySelector("#speaker-only-note")
    if (speakersField.selectedOptions.length === 0) {
        makePlaceholderActive(document.querySelector("#placeholder-submission"))
        makePlaceholderActive(document.querySelector("#placeholder-slot"))
        if (note) note.classList.add("d-none")
    } else {
        makePlaceholderInactive(
            document.querySelector("#placeholder-submission"),
        )
        makePlaceholderInactive(document.querySelector("#placeholder-slot"))
        if (note) note.classList.remove("d-none")
    }
}

const placeholderSidebarQuery = window.matchMedia("(min-width: 993px)")

const syncPlaceholderCollapse = () => {
    const toggle = document.querySelector("#placeholder-toggle")
    const list = document.querySelector("#placeholder-list")
    if (!toggle || !list) return
    const isSidebar = placeholderSidebarQuery.matches
    if (isSidebar) {
        toggle.setAttribute("tabindex", "-1")
    } else {
        toggle.removeAttribute("tabindex")
    }
    toggle.setAttribute("aria-expanded", isSidebar)
    list.setAttribute("aria-hidden", !isSidebar)
    list.classList.toggle("show", isSidebar)
}

const blockSidebarPlaceholderToggle = (event) => {
    if (!placeholderSidebarQuery.matches) return
    if (!event.target.closest("#placeholder-toggle")) return
    event.stopPropagation()
    event.preventDefault()
}

const invalidatePreview = () => {
    document.querySelectorAll(".submit-group button").forEach((button) => {
        if (button.value !== "preview") button.classList.add("d-none")
    })
    document
        .querySelectorAll(
            "#mail-editor-warnings, #mail-editor-preview, #mail-editor-skip-queue-confirm",
        )
        .forEach((element) => {
            element.classList.add("d-none")
        })
}

onReady(() => {
    lastFocusedInput = document.querySelector("#id_text_0")

    syncPlaceholderCollapse()
    placeholderSidebarQuery.addEventListener("change", syncPlaceholderCollapse)
    const placeholderColumn = document.querySelector("#placeholder-column")
    if (placeholderColumn) {
        placeholderColumn.addEventListener(
            "click",
            blockSidebarPlaceholderToggle,
            true,
        )
    }

    const editorForm = document.querySelector("form.form-with-placeholder")
    if (editorForm) {
        editorForm.addEventListener("input", invalidatePreview)
        editorForm.addEventListener("change", invalidatePreview)
    }

    // When an input matching id_text_\d or id_subject\d is focused, set lastFocusedInput to that input
    document
        .querySelectorAll('textarea[id^="id_text_"], input[id^="id_subject"]')
        .forEach((input) => {
            input.addEventListener("focus", () => {
                lastFocusedInput = input
            })
        })

    // When any placeholder is clicked, insert its text into lastFocusedInput
    document.querySelectorAll(".placeholder").forEach((placeholder) => {
        placeholder.addEventListener("click", (e) => {
            if (e.target.closest('[data-toggle="collapse"]')) {
                return
            }
            if (lastFocusedInput) {
                const placeholderValue = "{" + placeholder.dataset.placeholder + "}"
                const content = lastFocusedInput.value
                let start = lastFocusedInput.selectionStart
                let end = lastFocusedInput.selectionEnd
                const selectedPlaceholderStart = /\{\w*$/.exec(
                    content.substring(0, start),
                )
                var selectedPlaceholderEnd = /^\w*\}/.exec(
                    content.substring(end),
                )
                if (selectedPlaceholderStart) {
                    start -= selectedPlaceholderStart[0].length
                }
                if (selectedPlaceholderEnd) {
                    end += selectedPlaceholderEnd[0].length
                }

                lastFocusedInput.value =
                    content.substring(0, start) +
                    placeholderValue +
                    content.substring(end)
                lastFocusedInput.selectionStart = start
                lastFocusedInput.selectionEnd = start + placeholderValue.length
                lastFocusedInput.focus()
                invalidatePreview()
            }
        })
    })

    // When an individual speaker is added, hide all placeholders that are proposal-specific
    const speakersField = document.querySelector("#id_speakers")
    if (speakersField) {
        speakersField.addEventListener("change", () => {
            updateVisiblePlaceholders(speakersField)
        })
        updateVisiblePlaceholders(speakersField)
    }

    const managedField = document.querySelector("#id_managed_recipients")
    if (managedField) {
        const updateAccountPlaceholders = () => {
            const hide = managedField.value === "only"
            document
                .querySelectorAll(".placeholder[data-account-required]")
                .forEach((el) => {
                    el.classList.toggle("d-none", hide)
                })
        }
        managedField.addEventListener("change", updateAccountPlaceholders)
        updateAccountPlaceholders()
    }
})
