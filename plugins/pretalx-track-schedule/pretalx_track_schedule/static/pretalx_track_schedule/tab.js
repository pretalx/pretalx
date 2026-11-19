// Adds the "By track" tab to the schedule pages' tab bar (see
// signals.add_header_tab), after pretalx's own tabs and before the
// organiser's header links, which open in a new tab.
(() => {
    const addTab = () => {
        const meta = document.querySelector('meta[name="track-schedule-tab"]')
        const tabs = document.getElementById("header-tabs")
        if (!meta || !tabs) return
        const url = meta.dataset.url
        if ([...tabs.querySelectorAll("a")].some((a) => a.getAttribute("href") === url)) return
        const tab = document.createElement("a")
        tab.href = url
        tab.className = "header-tab"
        if (window.location.pathname === url) tab.classList.add("active")
        const icon = document.createElement("i")
        icon.className = "fa fa-columns"
        tab.append(icon, ` ${meta.dataset.label}`)
        // pretalx's own tabs; organiser header links go through /redirect/
        const ownTabs = [...tabs.querySelectorAll(":scope > a.header-tab")].filter(
            (a) => !a.getAttribute("href").startsWith("/redirect/"),
        )
        if (ownTabs.length) ownTabs[ownTabs.length - 1].after(tab)
        else tabs.prepend(tab)
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", addTab)
    else addTab()
})()
