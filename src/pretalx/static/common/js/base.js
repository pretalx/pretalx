// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* This file will be loaded on all pretalx pages.
 * It will be loaded before all other scripts. */

/* This function makes sure a given function is run after the DOM is fully loaded.
 * Nearly all of our scripts are loaded deferred, so this SHOULD always run sync,
 * but it's a cheap safety hook to use. */
const onReady = (fn) => {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", fn)
    } else {
        fn()
    }
}

/* Use for all requests to the organiser area, so that sessions running into
 * a timeout do not break. */
const orgaFetch = (url, options) => {
    options = options || {}
    const headers = Object.assign({}, options.headers, {
        "X-Requested-With": "XMLHttpRequest",
    })
    return window.fetch(url, Object.assign({}, options, { headers })).then((response) => {
        const loginUrl = response.status === 401 && response.headers.get("X-Login-Url")
        if (!loginUrl) return response
        const current = window.location.pathname + window.location.search + window.location.hash
        window.top.location.href = `${loginUrl}?next=${encodeURIComponent(current)}`
        return new Promise(() => {})
    })
}

/* Allow scripts to make a field visible before we scroll to it, e.g. by opening
 * a tab or collapsed section. */
const fieldRevealHooks = []
const registerFieldRevealHook = (hook) => {
    fieldRevealHooks.push(hook)
}

const FOCUSABLE_SELECTOR = "input:not([type=hidden]), select, textarea, button, [tabindex]:not([tabindex='-1'])"
const isFieldVisible = (element) => element.getClientRects().length > 0
const getFocusTarget = (element, group) => {
    if (element.matches(FOCUSABLE_SELECTOR) && isFieldVisible(element)) return element
    const label = group.querySelector("label[for]")
    const labelled = label && document.getElementById(label.htmlFor)
    if (labelled && labelled.matches(FOCUSABLE_SELECTOR) && isFieldVisible(labelled)) return labelled
    for (const candidate of group.querySelectorAll(FOCUSABLE_SELECTOR)) {
        if (isFieldVisible(candidate)) return candidate
    }
    group.setAttribute("tabindex", "-1")
    return group
}

const scrollToField = (element, { focus = false } = {}) => {
    if (!element) return
    fieldRevealHooks.forEach((hook) => hook(element))
    for (let details = element.closest("details:not([open])"); details; details = details.parentElement.closest("details:not([open])")) {
        details.open = true
    }
    const group = element.closest(".form-group") || element
    group.scrollIntoView({ block: "center" })
    if (focus) getFocusTarget(element, group).focus({ preventScroll: true })
}

const jumpToPage = (link) => {
    const maxPage = parseInt(link.dataset.maxPage, 10)
    const input = window.prompt(link.dataset.promptText)
    if (!input) return

    const page = parseInt(input, 10)
    if (!page || page < 1 || page > maxPage) {
        window.alert(link.dataset.invalidText)
        return
    }
    const url = link.dataset.pageHref.replace("_PAGE_", page)

    const tableContent = link.closest(".table-content")
    if (tableContent?.id && typeof htmx !== "undefined") {
        const target = `#${tableContent.id}`
        link.setAttribute("hx-indicator", target)
        link.dataset.scrollToTable = "true"
        htmx.ajax("GET", url, { target, swap: "innerHTML", source: link })
        return
    }
    window.location.href = url
}

document.addEventListener("click", (event) => {
    const link = event.target.closest?.("a.pagination-selection")
    if (!link) return
    event.preventDefault()
    jumpToPage(link)
})
