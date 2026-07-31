// SPDX-FileCopyrightText: 2024-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const FORMAT_ARGS = { hour: "numeric", minute: "2-digit" }
const RANGE_FORMAT_ARGS = { hour: "2-digit", minute: "2-digit", hour12: false }
const DATE_FORMAT_ARGS = { year: "numeric", month: "numeric", day: "numeric" }

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

const pad = (value) => String(value).padStart(2, "0")

const getLocalDate = (date) => {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const crossesDate = (isoString, date) =>
    isoString.slice(0, 10) !== getLocalDate(date)

const DJANGO_DATE_TOKENS = {
    Y: (date) => String(date.getFullYear()),
    y: (date) => pad(date.getFullYear() % 100),
    m: (date) => pad(date.getMonth() + 1),
    n: (date) => String(date.getMonth() + 1),
    d: (date) => pad(date.getDate()),
    j: (date) => String(date.getDate()),
}

const formatDjangoDate = (date, format) => {
    if (!format) return null
    let result = ""
    for (let index = 0; index < format.length; index++) {
        const char = format[index]
        if (char === "\\") {
            index += 1
            if (index < format.length) result += format[index]
            continue
        }
        const token = DJANGO_DATE_TOKENS[char]
        if (token) {
            result += token(date)
        } else if (/[a-zA-Z]/.test(char)) {
            return null
        } else {
            result += char
        }
    }
    return result
}

const formatLocalDate = (date) =>
    formatDjangoDate(date, document.body.dataset.shortdateformat) ||
    date.toLocaleDateString(undefined, DATE_FORMAT_ARGS)

const formatLocal = (date, formatArgs, withDate) => {
    const timeString = date.toLocaleString(undefined, formatArgs)
    return withDate ? `${formatLocalDate(date)} ${timeString}` : timeString
}

const buildLocalTimeHint = (timeString) => {
    const tzString = Intl.DateTimeFormat()
        .resolvedOptions()
        .timeZone.replace(/_/g, " ")
    const hint = document.createElement("span")
    hint.classList.add("timezone-help")
    const icon = document.createElement("i")
    icon.className = "fa fa-globe"
    icon.setAttribute("aria-hidden", "true")
    const label = document.createElement("span")
    label.className = "sr-only"
    label.textContent = document.body.dataset.localtimeLabel
    const detail = document.body.dataset.localtimeFormat
        .replace("{time}", timeString)
        .replace("{timezone}", tzString)
    hint.append(icon, label, ` ${detail}`)
    return hint
}

const addLocalTimeRange = (element) => {
    const start = element.querySelector("time[datetime]")
    const end = element.querySelector("time[datetime]:last-of-type")
    const startIso = start.dataset.isodatetime || start.getAttribute("datetime")
    const endIso = end.dataset.isodatetime || end.getAttribute("datetime")

    const startDate = new Date(startIso)
    const endDate = new Date(endIso)

    const startOffset = getOffsetFromIso(startIso)
    if (startOffset === startDate.getTimezoneOffset()) return // same timezone at event time

    const spansTwoLocalDays = getLocalDate(endDate) !== getLocalDate(startDate)
    const startString = formatLocal(
        startDate,
        RANGE_FORMAT_ARGS,
        crossesDate(startIso, startDate) || spansTwoLocalDays,
    )
    const endString = formatLocal(endDate, RANGE_FORMAT_ARGS, spansTwoLocalDays)

    element.appendChild(buildLocalTimeHint(`${startString}-${endString}`))
}

const addLocalTime = (element) => {
    const isoString = element.dataset.isodatetime || element.getAttribute("datetime")
    const elementOffset = getOffsetFromIso(isoString)
    const date = new Date(isoString)
    if (elementOffset === date.getTimezoneOffset()) return // same timezone at event time

    const localString = formatLocal(
        date,
        FORMAT_ARGS,
        crossesDate(isoString, date),
    )
    element.insertAdjacentElement("afterend", buildLocalTimeHint(localString))
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
