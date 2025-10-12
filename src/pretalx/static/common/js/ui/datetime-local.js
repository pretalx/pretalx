// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const utcoffset = new Date().getTimezoneOffset()
const FORMAT_ARGS = { hour: "numeric", minute: "2-digit" }

const getOffsetFromIso = (isoString) => {
    if (isoString.endsWith("Z")) return 0 // UTC
    // Match offset in tz string like "2025-10-03T14:30:00+02:00"
    const match = isoString.match(/([+-]\d{2}):?(\d{2})$/)
    if (!match) return 0 // No timezone offset, no mercy.
    const hours = parseInt(match[1])
    const minutes =
        Math.abs(hours) === hours ? parseInt(match[2]) : -parseInt(match[2])
    return -(hours * 60 + minutes) // negative because getTimezoneOffset is backwards
}

const addLocalTimeRange = (element) => {
    const start = element.querySelector("time[datetime]")
    const end = element.querySelector("time[datetime]:last-of-type")
    const startIso = start.dataset.isodatetime || start.getAttribute("datetime")
    const endIso = end.dataset.isodatetime || end.getAttribute("datetime")

    const startOffset = getOffsetFromIso(startIso)
    if (startOffset === utcoffset) return // same timezone

    const startDate = new Date(startIso)
    const endDate = new Date(endIso)

    const startString = startDate.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    })
    const endString = endDate.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    })

    const tzString = Intl.DateTimeFormat().resolvedOptions().timeZone
    const helpText = document.createElement("span")
    helpText.classList.add("timezone-help")
    helpText.innerHTML = `<i class="fa fa-globe"></i> ${startString}-${endString} (${tzString})`
    element.appendChild(helpText)
}

const addLocalTime = (element) => {
    const isoString = element.getAttribute("datetime")
    const elementOffset = getOffsetFromIso(isoString)
    if (elementOffset === utcoffset) return

    const date = new Date(isoString)
    const localString = date.toLocaleString(undefined, FORMAT_ARGS)
    const tzString = Intl.DateTimeFormat().resolvedOptions().timeZone
    const helpText = document.createElement("span")
    helpText.classList.add("timezone-help")
    helpText.innerHTML = `<i class="fa fa-globe"></i> ${localString} (${tzString})`
    element.insertAdjacentElement("afterend", helpText)
}

onReady(() => {
    document.querySelectorAll("time[datetime]").forEach((element) => {
        if (!element.parentElement.classList.contains("timerange-block")) {
            addLocalTime(element)
        }
    })
    document.querySelectorAll(".timerange-block").forEach((element) => {
        addLocalTimeRange(element)
    })
})
