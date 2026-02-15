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
    inputElement.addEventListener("input", handleInput, false)
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
    element.querySelectorAll("input[role=tab]").forEach((tab) => {
        tab.addEventListener("change", updateTabPanels)
    })

    // Keyboard shortcuts
    const toolbar = element.querySelector("markdown-toolbar")
    if (!toolbar) return

    const shortcutMap = {
        b: "md-bold",
        i: "md-italic",
        e: "md-code",
        k: "md-link",
    }
    const shiftShortcutMap = {
        7: "md-ordered-list",
        8: "md-unordered-list",
    }

    inputElement.addEventListener("keydown", (e) => {
        if (!(e.ctrlKey || e.metaKey)) return

        if (!e.shiftKey && shortcutMap[e.key]) {
            e.preventDefault()
            toolbar.querySelector(shortcutMap[e.key])?.click()
        } else if (e.shiftKey && shiftShortcutMap[e.key]) {
            e.preventDefault()
            toolbar.querySelector(shiftShortcutMap[e.key])?.click()
        }
    })

    // Ctrl+V: paste URL as markdown link when text is selected
    inputElement.addEventListener("paste", (e) => {
        const { selectionStart, selectionEnd } = inputElement
        if (selectionStart === selectionEnd) return
        const url = e.clipboardData.getData("text")
        if (!url.startsWith("http://") && !url.startsWith("https://")) return
        e.preventDefault()
        const selected = inputElement.value.slice(selectionStart, selectionEnd)
        document.execCommand("insertText", false, `[${selected}](${url})`)
    })

    // Ctrl+Shift+P: toggle Write/Preview (on wrapper so it works from preview too)
    element.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "p") {
            e.preventDefault()
            const unchecked = element.querySelector("input[role=tab]:not(:checked)")
            if (unchecked) {
                unchecked.checked = true
                unchecked.dispatchEvent(new Event("change", { bubbles: true }))
            }
        }
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
