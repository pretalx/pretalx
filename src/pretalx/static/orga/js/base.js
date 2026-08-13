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

const PALETTE_ICONS = {
    organiser: "fa-users",
    user: "fa-user",
    "user.admin": "fa-user",
    submission: "fa-sticky-note-o",
    speaker: "fa-microphone",
}

const makePaletteRow = ({url, type, color, title, meta}) => {
    const row = document.createElement("a")
    row.className = "palette-row"
    // Only allow safe URLs — the URL comes from the server but guard against
    // javascript: schemes defensively.
    try {
        const parsed = new URL(url, window.location.origin)
        if (parsed.protocol === "http:" || parsed.protocol === "https:") {
            row.href = parsed.href
        }
    } catch (_) { /* leave href unset */ }

    if (color && /^#[0-9a-f]{3,8}$/i.test(color)) {
        const swatch = document.createElement("span")
        swatch.className = "palette-row-swatch"
        swatch.style.background = color
        row.appendChild(swatch)
    } else {
        const icon = document.createElement("i")
        icon.className = `fa ${PALETTE_ICONS[type] || "fa-angle-right"} palette-row-icon`
        icon.setAttribute("aria-hidden", "true")
        row.appendChild(icon)
    }

    const text = document.createElement("span")
    text.className = "palette-row-text"
    const name = document.createElement("span")
    name.className = "palette-row-title"
    name.textContent = title ?? ""
    text.appendChild(name)
    if (meta) {
        const metaEl = document.createElement("span")
        metaEl.className = "palette-row-meta"
        metaEl.textContent = meta
        text.appendChild(metaEl)
    }
    row.appendChild(text)
    return row
}

const paletteResultMeta = (res) => {
    if (res.type === "event") {
        return [res.organiser, res.date_range].filter(Boolean).join(" · ")
    }
    if (res.type === "user.admin") return res.email
    return res.event || ""
}

const initCommandPalette = () => {
    const dialog = document.querySelector("#command-palette")
    if (!dialog) return
    const searchWrapper = dialog.querySelector("#palette-search")
    const searchInput = dialog.querySelector("#palette-input")
    const quickActions = dialog.querySelector("#palette-quick-actions")
    const eventsSection = dialog.querySelector("#palette-events")
    const eventList = dialog.querySelector("#palette-event-list")
    const allEventsRow = dialog.querySelector("#palette-all-events")
    const resultsLabel = dialog.querySelector("#palette-results-label")
    const searchResults = dialog.querySelector("#search-results")
    const loadingTemplate = searchResults.querySelector(".search-loading")
    const apiURL = searchWrapper.getAttribute("data-source")
    const organiser = searchWrapper.getAttribute("data-organiser")
    const queryStr = "?" + (organiser ? `organiser=${encodeURIComponent(organiser)}&` : "") + "query="

    const visibleRows = () => Array.from(dialog.querySelectorAll("a.palette-row")).filter((row) => row.offsetParent !== null)
    const select = (row) => {
        dialog.querySelectorAll("a.palette-row.active").forEach((el) => el.classList.remove("active"))
        if (!row) return
        row.classList.add("active")
        row.scrollIntoView({block: "nearest"})
    }
    const selectFirst = () => select(visibleRows()[0])
    const moveSelection = (delta) => {
        const rows = visibleRows()
        if (!rows.length) return
        const current = rows.indexOf(dialog.querySelector("a.palette-row.active"))
        if (current === -1) {
            select(delta > 0 ? rows[0] : rows[rows.length - 1])
        } else {
            select(rows[(current + delta + rows.length) % rows.length])
        }
    }
    const clearResults = () => {
        searchResults.querySelectorAll(":scope > *:not(.search-loading)").forEach((el) => el.remove())
    }

    let loadIndicatorTimeout = null
    const showLoadIndicator = () => {
        if (searchResults.querySelector(".loading")) return
        const loadingEl = loadingTemplate.cloneNode(true)
        loadingEl.classList.remove("d-none", "search-loading")
        loadingEl.classList.add("loading")
        loadingEl.querySelector(".loading-spinner")?.classList.add("loading-spinner-xl")
        searchResults.replaceChildren(loadingTemplate, loadingEl)
    }

    let eventsLoaded = false
    let hasEvents = false
    const loadEvents = () => {
        if (eventsLoaded) return
        eventsLoaded = true
        fetch(apiURL + queryStr).then((response) => response.json()).then((data) => {
            eventList.replaceChildren(...data.results.map((res) => makePaletteRow({
                url: res.url,
                type: res.type,
                color: res.color,
                title: res.name,
                meta: paletteResultMeta(res),
            })))
            hasEvents = !!data.results.length
            if (data.has_more_events) allEventsRow.classList.remove("d-none")
            if (searchInput.value) return
            eventsSection.classList.toggle("d-none", !hasEvents)
            selectFirst()
        })
    }

    const quickActionRows = quickActions ? Array.from(quickActions.querySelectorAll("a.palette-row")) : []
    const quickActionHaystack = (row) => {
        const label = row.querySelector(".palette-row-text")?.textContent || ""
        const shortcut = row.getAttribute("data-palette-shortcut") || ""
        return [label, shortcut, shortcut.replace(/\s+/g, "")].join(" ").toLowerCase()
    }
    const filterQuickActions = (query) => {
        if (!quickActions) return
        const needle = query.trim().toLowerCase()
        let matches = 0
        quickActionRows.forEach((row) => {
            const hit = !needle || quickActionHaystack(row).includes(needle)
            row.classList.toggle("d-none", !hit)
            if (hit) matches += 1
        })
        quickActions.classList.toggle("d-none", !matches)
    }

    let lastQuery = null
    const triggerSearch = () => {
        const thisQuery = searchInput.value
        if (thisQuery === lastQuery) return
        lastQuery = thisQuery
        filterQuickActions(thisQuery)
        eventsSection.classList.toggle("d-none", !!thisQuery || !hasEvents)
        if (loadIndicatorTimeout) clearTimeout(loadIndicatorTimeout)

        if (!thisQuery) {
            clearResults()
            resultsLabel.classList.add("d-none")
            selectFirst()
            return
        }
        loadIndicatorTimeout = setTimeout(showLoadIndicator, 80)

        fetch(apiURL + queryStr + encodeURIComponent(thisQuery)).then((response) => {
            if (thisQuery !== lastQuery) {
                // Ignore this response, it's for an old query
                return
            }
            if (loadIndicatorTimeout) clearTimeout(loadIndicatorTimeout)

            response.json().then((data) => {
                clearResults()
                data.results.forEach((res) => {
                    searchResults.append(makePaletteRow({
                        url: res.url,
                        type: res.type,
                        color: res.color,
                        title: res.name,
                        meta: paletteResultMeta(res),
                    }))
                })
                resultsLabel.classList.toggle("d-none", !data.results.length)
                selectFirst()
            }) /* response.json().then */
        }) /* fetch.then */
    }

    searchInput.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") {
            dialog.close()
        } else if (ev.key === "Enter") {
            const selected = dialog.querySelector("a.palette-row.active")
            if (!selected?.href) return
            location.href = selected.href
        } else if (ev.key === "ArrowDown") {
            moveSelection(1)
        } else if (ev.key === "ArrowUp") {
            moveSelection(-1)
        } else {
            return
        }
        ev.preventDefault()
        ev.stopPropagation()
    })

    searchInput.addEventListener("input", () => {triggerSearch()})

    const openPalette = () => {
        if (dialog.open) return
        dialog.showModal()
        searchInput.focus()
        loadEvents()
        selectFirst()
    }
    dialog.addEventListener("close", () => {
        searchInput.value = ""
        lastQuery = null
        clearResults()
        filterQuickActions("")
        eventsSection.classList.toggle("d-none", !hasEvents)
        resultsLabel.classList.add("d-none")
        select(null)
    })

    document.addEventListener("keydown", (ev) => {
        if (ev.altKey && ev.key === "k") {
            openPalette()
            ev.preventDefault()
            ev.stopPropagation()
        }
    })

    let chordPrefix = null
    let chordTimeout = null
    const resetChord = () => {
        chordPrefix = null
        if (chordTimeout) clearTimeout(chordTimeout)
        chordTimeout = null
    }
    document.addEventListener("keydown", (ev) => {
        if (dialog.open || ev.altKey || ev.ctrlKey || ev.metaKey) return
        if (ev.target instanceof Element && ev.target.closest("input, textarea, select, [contenteditable=true]")) return
        const key = ev.key.toLowerCase()
        if (!/^[a-z]$/.test(key)) {
            resetChord()
            return
        }
        if (chordPrefix) {
            const row = document.querySelector(`[data-palette-shortcut="${chordPrefix} ${key}"]`)
            resetChord()
            if (row?.href) {
                location.href = row.href
                ev.preventDefault()
            }
            return
        }
        if (key === "g") {
            chordPrefix = key
            chordTimeout = setTimeout(resetChord, 1500)
            ev.preventDefault()
        }
    })

    document.querySelectorAll("[data-palette-trigger]").forEach((trigger) => {
        trigger.addEventListener("click", openPalette)
    })
}

document.addEventListener("htmx:configRequest", (e) => {
    e.detail.headers["X-CSRFToken"] = getCookie("pretalx_csrftoken")
})

const isSidebarCollapsed = () => document.documentElement.classList.contains("sidebar-collapsed")
const setSidebarCollapsed = (collapsed) => {
    document.documentElement.classList.toggle("sidebar-collapsed", collapsed)
    const sidebar = document.querySelector("aside.sidebar")
    sidebar?.classList.toggle("sidebar-rail-locked", collapsed && sidebar.matches(":hover"))
    document.querySelector("#sidebar-collapse-toggle")?.setAttribute("aria-expanded", collapsed ? "false" : "true")
    try {
        localStorage.setItem("sidebarVisible", collapsed ? "0" : "1")
    } catch (e) {
        // localStorage can be unavailable
    }
}

onReady(() => {
    const burger = document.querySelector("[data-toggle=sidebar]")
    const sidebar = document.querySelector("aside.sidebar")
    const footToggle = document.querySelector("#sidebar-collapse-toggle")
    const isNarrow = window.matchMedia("(max-width: 768px)")

    if (sidebar && burger) {
        burger.addEventListener("click", (ev) => {
            ev.preventDefault()
            if (isNarrow.matches) sidebar.classList.toggle("sidebar-open")
            else setSidebarCollapsed(!isSidebarCollapsed())
        })
    }
    if (footToggle) {
        footToggle.addEventListener("click", () => setSidebarCollapsed(!isSidebarCollapsed()))
        footToggle.setAttribute("aria-expanded", isSidebarCollapsed() ? "false" : "true")
    }
    sidebar?.addEventListener("mouseleave", () => sidebar.classList.remove("sidebar-rail-locked"))
    initCommandPalette()
})
