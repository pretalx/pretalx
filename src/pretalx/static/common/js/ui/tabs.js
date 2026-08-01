// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const TAB_SELECTOR = "input[role=tab][name=tablist]"
const ERROR_SELECTOR = "[aria-invalid=true], .is-invalid, .invalid-feedback"

const updateTabPanels = () => {
    const selectedTab = document.querySelector(`${TAB_SELECTOR}:checked`)
    if (!selectedTab) return
    const selectedPanel = document.getElementById(selectedTab.getAttribute("aria-controls"))
    if (!selectedPanel) return
    selectedTab.parentElement.querySelectorAll(`[role=tab][aria-selected=true]`).forEach((element) => {
        element.setAttribute("aria-selected", "false")
    })
    selectedPanel.parentElement.querySelectorAll("[role=tabpanel][aria-hidden=false]").forEach((element) => {
        element.setAttribute("aria-hidden", "true")
    })
    selectedTab.setAttribute("aria-selected", "true")
    selectedPanel.setAttribute("aria-hidden", "false")
    window.location.hash = selectedTab.id
}

const getTabFromHash = () => {
    const fragment = window.location.hash.substr(1)
    if (fragment) {
        return document.querySelector(`${TAB_SELECTOR}#${fragment}`)
    }
}

const getTabForElement = (element) => {
    const panel = element.closest("[role=tabpanel]")
    if (!panel || !panel.id) return
    return document.querySelector(`${TAB_SELECTOR}[aria-controls="${panel.id}"]`)
}

const getFirstErrorInTabs = () => {
    for (const element of document.querySelectorAll(ERROR_SELECTOR)) {
        const tab = getTabForElement(element)
        if (tab) return { element, tab }
    }
    return {}
}

const revealTabFor = (element) => {
    const tab = getTabForElement(element)
    if (tab && !tab.checked) {
        tab.checked = true
        updateTabPanels()
    }
}

const initInvalidHandling = () => {
    let handledInvalid = false
    document.addEventListener("invalid", (event) => {
        if (handledInvalid) return
        handledInvalid = true
        window.setTimeout(() => { handledInvalid = false }, 0)

        // Auto-focus is fine here, as it happens as a response to a user action
        scrollToField(event.target, { focus: true })
    }, true)
}

const initTabs = () => {
    // If the server rejected a field, show its tab. Otherwise, check if there is
    // a tab selected by the hash. If not:
    // Fall back to the last selected tab, and failing that, the first tab

    registerFieldRevealHook(revealTabFor)

    const firstError = getFirstErrorInTabs()
    let selectedTab = firstError.tab
    if (!selectedTab) { selectedTab = getTabFromHash() }
    if (!selectedTab) { selectedTab = document.querySelector(`${TAB_SELECTOR}:checked`) }
    if (!selectedTab) { selectedTab = document.querySelector(TAB_SELECTOR) }
    if (!selectedTab) return

    selectedTab.checked = true
    updateTabPanels()

    if (firstError.element) {
        scrollToField(firstError.element)
    }

    document.querySelectorAll(`${TAB_SELECTOR}`).forEach((element) => {
        element.addEventListener('change', updateTabPanels)
    })

    initInvalidHandling()

    // If the URL fragment changes, e.g. by navigating backwards, update the tab
    window.addEventListener('hashchange', () => {
        selectedTab = getTabFromHash()
        if (selectedTab) {
            selectedTab.checked = true
            updateTabPanels()
        }
    })
}

onReady(() => {
    if (document.querySelector(TAB_SELECTOR)) {
      initTabs()
    }
})
