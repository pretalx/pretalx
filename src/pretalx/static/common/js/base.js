// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

/* This file will be loaded on all pretalx pages.
 * It will be loaded before all other scripts. */

/* This function makes sure a given function is run after the DOM is fully loaded. */
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
