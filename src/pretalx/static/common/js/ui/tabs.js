// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const TAB_SELECTOR = "input[role=tab][name=tablist]"

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

const revealTabFor = (element) => {
    const tab = getTabForElement(element)
    if (tab && !tab.checked) {
        tab.checked = true
        updateTabPanels()
    }
}

const initTabs = () => {
    // Pick tab: 1. selected by hash, 2. last selected, 3. first tab
    registerFieldRevealHook(revealTabFor)

    let selectedTab = getTabFromHash()
    if (!selectedTab) { selectedTab = document.querySelector(`${TAB_SELECTOR}:checked`) }
    if (!selectedTab) { selectedTab = document.querySelector(TAB_SELECTOR) }
    if (!selectedTab) return

    selectedTab.checked = true
    updateTabPanels()

    document.querySelectorAll(`${TAB_SELECTOR}`).forEach((element) => {
        element.addEventListener('change', updateTabPanels)
    })

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
