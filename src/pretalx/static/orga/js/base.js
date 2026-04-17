// SPDX-FileCopyrightText: 2018-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const getCookie = (name) => {
    let cookieValue = null
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";")
        for (var i = 0; i < cookies.length; i++) {
            let cookie = cookies[i].trim()
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === name + "=") {
                cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1),
                )
                break
            }
        }
    }
    return cookieValue
}

const makeSearchEl = (tag, className, text) => {
    const el = document.createElement(tag)
    if (className) el.className = className
    if (text !== undefined && text !== null) el.textContent = text
    return el
}
const makeSearchTitle = (name, iconTag, iconClass) => {
    const title = makeSearchEl("span", "search-title")
    if (iconTag) {
        title.appendChild(makeSearchEl(iconTag, `fa fa-fw ${iconClass}`))
        title.append(" ", name ?? "")
    } else {
        title.appendChild(makeSearchEl("span", null, name))
    }
    return title
}
const makeSearchDetail = (iconClass, text) => {
    const detail = makeSearchEl("span", "search-detail")
    detail.appendChild(makeSearchEl("span", iconClass))
    detail.append(" ", text ?? "")
    return detail
}

const initNavSearch = () => {
    const wrapper = document.querySelector("#nav-search-wrapper")
    const summary = wrapper.querySelector("summary")
    const searchInput = wrapper.querySelector("input")
    const searchWrapper = wrapper.querySelector("#nav-search-input-wrapper")
    const searchResults = searchWrapper.querySelector("#search-results")
    const loadingTemplate = searchResults.querySelector(".search-loading")
    const apiURL = searchWrapper.getAttribute("data-source")
    const queryStr = "?" + (typeof searchWrapper.getAttribute("data-organiser") !== "undefined" ? "&organiser=" + searchWrapper.getAttribute("data-organiser") : "") + "&query="

    let loadIndicatorTimeout = null
    const showLoadIndicator = () => {
        if (!searchWrapper.querySelector(".loading")) {
            const loadingEl = loadingTemplate.cloneNode(true)
            loadingEl.classList.remove("d-none", "search-loading")
            loadingEl.classList.add("loading")
            loadingEl.querySelector(".loading-spinner")?.classList.add("loading-spinner-xl")
            searchResults.replaceChildren(loadingTemplate, loadingEl)
        }
    }

    let lastQuery = null
    const triggerSearch = () => {
        if (searchInput.value === lastQuery) {
            return
        }
        searchInput.classList.remove("no-focus")

        const thisQuery = searchInput.value
        lastQuery = thisQuery
        if (loadIndicatorTimeout) clearTimeout(loadIndicatorTimeout)
        loadIndicatorTimeout = setTimeout(showLoadIndicator, 80)

        fetch(apiURL + queryStr + encodeURIComponent(searchInput.value)).then((response) => {
            if (thisQuery !== lastQuery) {
                // Ignore this response, it's for an old query
                return
            }
            if (loadIndicatorTimeout) clearTimeout(loadIndicatorTimeout)

            response.json().then((data) => {
                searchResults.querySelectorAll("li:not(.search-loading)").forEach((el) => el.remove())
                data.results.forEach((res) => {
                    const a = document.createElement("a")
                    // Only allow safe URLs — res.url comes from the server but guard against
                    // javascript: schemes defensively.
                    try {
                        const parsed = new URL(res.url, window.location.origin)
                        if (parsed.protocol === "http:" || parsed.protocol === "https:") {
                            a.href = parsed.href
                        }
                    } catch (_) { /* leave href unset */ }

                    if (res.type === "organiser" || res.type === "user") {
                        const icon = res.type === "organiser" ? "fa-users" : "fa-user"
                        a.appendChild(makeSearchTitle(res.name, "i", icon))
                    } else if (res.type === "user.admin") {
                        a.appendChild(makeSearchTitle(res.name))
                        a.appendChild(makeSearchDetail("fa fa-envelope-o fa-fw", res.email))
                    } else if (res.type === "submission" || res.type === "speaker") {
                        a.appendChild(makeSearchTitle(res.name))
                        a.appendChild(makeSearchDetail("fa fa-calendar fa-fw", res.event))
                    } else if (res.type === "event") {
                        a.appendChild(makeSearchTitle(res.name))
                        a.appendChild(makeSearchDetail("fa fa-users fa-fw", res.organiser))
                        a.appendChild(makeSearchDetail("fa fa-calendar fa-fw", res.date_range))
                    }

                    const li = document.createElement("li")
                    li.appendChild(a)
                    searchResults.append(li)
                }) /* data.results.forEach */
            }) /* response.json().then */
        }) /* fetch.then */
    }

    searchInput.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") {
            wrapper.removeAttribute("open")
            searchInput.value = ""
            searchInput.blur()
            ev.preventDefault()
            ev.stopPropagation()
        } else if (ev.key === "Enter") {
            const selected = searchWrapper.querySelector("li.active a")
            if (selected) {
                location.href = selected.href
                ev.preventDefault()
                ev.stopPropagation()
            }
        } else if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
            ev.preventDefault()
            ev.stopPropagation()
        }
    })

    searchInput.addEventListener("input", () => {triggerSearch()})

    // Focus search input when dropdown is expanded, and trigger empty search
    wrapper.addEventListener("click", () => {
        triggerSearch()
        setTimeout(() => {
            if (wrapper.getAttribute("open") === "") {
                searchInput.focus()
            } else {
                // Clear search input when dropdown is collapsed
                searchInput.value = ""
            }
        }, 0)
    })

    searchInput.addEventListener("keyup", (ev) => {
        const first = searchWrapper.querySelector("li:not(.search-loading)")
        const last = searchWrapper.querySelector("li:not(.search-loading):last-child")
        const selected = searchWrapper.querySelector("li.active")

        // Keyboard navigation: down
        if (ev.key === "ArrowDown") {
            const next = (selected && selected.nextElementSibling) ? selected.nextElementSibling : first
            if (!next) return
            searchInput.classList.add("no-focus")
            if (selected) { selected.classList.remove("active") }
            next.classList.add("active")
            ev.preventDefault()
            ev.stopPropagation()
        } else if (ev.key === "ArrowUp") {
            // Keyboard navigation: up
            const prev = (selected && selected.previousElementSibling) ? selected.previousElementSibling : last
            if (!prev || prev.classList.contains("search-loading")) return
            searchInput.classList.add("no-focus")
            if (selected) { selected.classList.remove("active") }
            prev.classList.add("active")
            ev.preventDefault()
            ev.stopPropagation()
        } else if (ev.key === "Enter") {
            // Keyboard navigation: enter
            ev.preventDefault()
            ev.stopPropagation()
            return true
        }
    })

    // Open search dropdown with alt+k
    document.addEventListener("keydown", (ev) => {
        if (ev.altKey && ev.key === "k") {
            if (summary.open) return
            summary.click()
            ev.preventDefault()
            ev.stopPropagation()
        }
    })
}

document.addEventListener("htmx:configRequest", (e) => {
    e.detail.headers["X-CSRFToken"] = getCookie("pretalx_csrftoken")
})

onReady(() => {
    const element = document.querySelector("[data-toggle=sidebar]")
    const sidebar = document.querySelector("aside.sidebar")
    const cls = "sidebar-uncollapsed"

    if (sidebar && localStorage["sidebarVisible"]) {
        sidebar.classList.add(cls)
        document.documentElement.classList.add('sidebar-expanded')
    }

    if (sidebar && element) {
        element.addEventListener("click", () => {
            sidebar.classList.toggle(cls)
            const isExpanded = sidebar.classList.contains(cls)

            localStorage["sidebarVisible"] = isExpanded ? "1" : ""
            document.documentElement.classList.toggle('sidebar-expanded', isExpanded)
        })
    }
    initNavSearch()
})
