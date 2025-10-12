// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* Handle Markdown: run marked on change and activate tabs */
let dirtyInputs = []
const options = {
    breaks: true,
    gfm: true,
    pedantic: false, // Drawback: will render lists without blank lines correctly
    silent: false,
    smartLists: true,
    tables: true,
}

const initMarkdown = (element) => {
    const inputElement = element.querySelector("textarea")
    const outputElement = element.querySelector(".markdown-preview .preview-content")
    if (!outputElement) return
    outputElement.innerHTML = DOMPurify.sanitize(
        marked.parse(inputElement.value, options),
    )
    const handleInput = () => {
        dirtyInputs.push(element)
    }
    inputElement.addEventListener("change", handleInput, false)
    inputElement.addEventListener("keyup", handleInput, false)
    inputElement.addEventListener("keypress", handleInput, false)
    inputElement.addEventListener("keydown", handleInput, false)

    // Activate tabs
    const updateTabPanels = (ev) => {
        const selectedTab = ev.target
            .closest("[role=tablist]")
            .querySelector("input[role=tab]:checked")
        if (!selectedTab) return
        const selectedPanel = document.getElementById(
            selectedTab.getAttribute("aria-controls"),
        )
        if (!selectedPanel) return
        selectedTab.parentElement
            .querySelectorAll(`[role=tab][aria-selected=true]`)
            .forEach((element) => {
                element.setAttribute("aria-selected", "false")
            })
        selectedPanel.parentElement
            .querySelectorAll("[role=tabpanel][aria-hidden=false]")
            .forEach((element) => {
                element.setAttribute("aria-hidden", "true")
            })
        selectedTab.setAttribute("aria-selected", "true")
        selectedPanel.setAttribute("aria-hidden", "false")
    }
    element.parentElement.querySelectorAll("input[role=tab]").forEach((tab) => {
        tab.addEventListener("change", updateTabPanels)
    })
}

const checkForChanges = () => {
    if (dirtyInputs.length) {
        dirtyInputs.forEach((element) => {
            const inputElement = element.querySelector("textarea")
            const outputElement = element.querySelector(".markdown-preview .preview-content")
            if (!outputElement) return
            outputElement.innerHTML = DOMPurify.sanitize(
                marked.parse(inputElement.value, options),
            )
        })
        dirtyInputs = []
    }
    window.setTimeout(checkForChanges, 100)
}

onReady(() => {
    document
        .querySelectorAll(".markdown-wrapper")
        .forEach((element) => initMarkdown(element))
    checkForChanges()
})
