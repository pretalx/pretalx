// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const crefOpenTarget = () => {
    if (!window.location.hash) return
    const target = document.getElementById(
        decodeURIComponent(window.location.hash.slice(1)),
    )
    if (target && target.tagName === "DETAILS") {
        target.open = true
        target.scrollIntoView({ block: "start" })
    }
}
window.addEventListener("hashchange", crefOpenTarget)

document.addEventListener("DOMContentLoaded", () => {
    crefOpenTarget()
    const input = document.getElementById("cref-search-input")
    const results = document.getElementById("cref-search-results")
    const dataElement = document.getElementById("cref-search-data")
    if (!input || !results || !dataElement) return

    const data = JSON.parse(dataElement.textContent)
    let activeIndex = -1

    const memberKinds = [
        ["methods", "method"],
        ["properties", "property"],
        ["attributes", "attribute"],
    ]

    const search = (query) => {
        query = query.toLowerCase()
        const primary = []
        const secondary = []
        const members = []
        for (const entry of data) {
            const name = entry.name.toLowerCase()
            if (name.startsWith(query)) {
                primary.push(entry)
            } else if (name.includes(query)) {
                secondary.push(entry)
            }
            if (entry.kind !== "class") continue
            for (const [key, anchor] of memberKinds) {
                for (const member of entry[key] || []) {
                    if (member.toLowerCase().includes(query)) {
                        members.push({
                            name: `${entry.name}.${member}`,
                            module: entry.module,
                            url: `${entry.url}#${anchor}-${member}`,
                            kind: anchor,
                            segment: entry.segment,
                            exact: member.toLowerCase().startsWith(query),
                        })
                    }
                }
            }
        }
        members.sort((a, b) => (b.exact - a.exact))
        return primary.concat(secondary, members).slice(0, 25)
    }

    const render = (matches) => {
        results.innerHTML = ""
        activeIndex = -1
        if (!matches.length) {
            results.hidden = true
            return
        }
        for (const match of matches) {
            const li = document.createElement("li")
            const a = document.createElement("a")
            a.href = match.url
            a.textContent = match.name
            const context = document.createElement("span")
            context.className = "cref-result-context"
            context.textContent = ` ${match.kind} · ${match.module}`
            li.appendChild(a)
            li.appendChild(context)
            results.appendChild(li)
        }
        results.hidden = false
    }

    const setActive = (index) => {
        const items = results.querySelectorAll("li")
        if (!items.length) return
        activeIndex = (index + items.length) % items.length
        items.forEach((item, i) =>
            item.classList.toggle("cref-active", i === activeIndex),
        )
        items[activeIndex].scrollIntoView({ block: "nearest" })
    }

    input.addEventListener("input", () => {
        const query = input.value.trim()
        if (query.length < 2) {
            results.hidden = true
            results.innerHTML = ""
            return
        }
        render(search(query))
    })

    input.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
            event.preventDefault()
            setActive(activeIndex + 1)
        } else if (event.key === "ArrowUp") {
            event.preventDefault()
            setActive(activeIndex - 1)
        } else if (event.key === "Enter") {
            const target = results.querySelector(
                activeIndex >= 0 ? "li.cref-active a" : "li a",
            )
            if (target) window.location.href = target.href
        } else if (event.key === "Escape") {
            results.hidden = true
        }
    })

    document.addEventListener("click", (event) => {
        if (!results.contains(event.target) && event.target !== input) {
            results.hidden = true
        }
    })
})
