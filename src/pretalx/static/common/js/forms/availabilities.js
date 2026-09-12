// SPDX-FileCopyrightText: 2017-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const initAvailabilities = (element) => {
    if (element.nextElementSibling?.classList.contains("availabilities-editor")) {
        return
    }

    const QUARTER = 15
    const DAY_MINUTES = 24 * 60
    const DAY_MS = 24 * 60 * 60 * 1000
    const ROW_HEIGHT = { 15: 14, 30: 22, 60: 34 }

    const data = JSON.parse(element.getAttribute("value"))
    let strings = {}
    try {
        strings = JSON.parse(element.dataset.strings)
    } catch {
        strings = {}
    }
    const editable = !element.hasAttribute("disabled")

    const pad = (value) => String(value).padStart(2, "0")
    const clock = (minute) => `${pad(Math.floor(minute / 60))}:${pad(minute % 60)}`
    const escapeHtml = (value) =>
        String(value ?? "").replace(
            /[&<>"']/g,
            (character) =>
                ({
                    "&": "&amp;",
                    "<": "&lt;",
                    ">": "&gt;",
                    '"': "&quot;",
                    "'": "&#39;",
                })[character],
        )

    const locale = document.documentElement.lang || undefined
    const dateFormat = (options) => {
        try {
            return new Intl.DateTimeFormat(locale, options)
        } catch {
            return new Intl.DateTimeFormat(undefined, options)
        }
    }
    const weekdayFormat = dateFormat({ weekday: "short", timeZone: "UTC" })
    const dayMonthFormat = dateFormat({
        day: "numeric",
        month: "short",
        timeZone: "UTC",
    })
    const zoneFormat = new Intl.DateTimeFormat("en-US", {
        timeZone: data.event.timezone,
        hourCycle: "h23",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    })

    const wallClock = (timestamp) => {
        const parts = {}
        for (const part of zoneFormat.formatToParts(new Date(timestamp))) {
            parts[part.type] = part.value
        }
        return {
            date: Date.UTC(
                Number(parts.year),
                Number(parts.month) - 1,
                Number(parts.day),
            ),
            minute: Number(parts.hour) * 60 + Number(parts.minute),
        }
    }
    const offsetAt = (timestamp) => {
        const wall = wallClock(timestamp)
        return wall.date + wall.minute * 60000 - timestamp
    }
    const wallClockToTimestamp = (date, minute) => {
        const target = date + minute * 60000
        const first = offsetAt(target)
        const second = offsetAt(target - first)
        if (second === first) return target - first
        const third = offsetAt(target - second)
        if (third === second) return target - second
        return target - Math.min(second, third)
    }

    const parseDate = (value) => {
        const [year, month, day] = String(value).split("-").map(Number)
        return Date.UTC(year, month - 1, day)
    }
    const firstDate = parseDate(data.event.date_from)
    const dayCount = Math.max(
        1,
        Math.round((parseDate(data.event.date_to) - firstDate) / DAY_MS) + 1,
    )
    const dayStart = []
    const dayEnd = []
    const dayLinear = []
    const dayGaps = []
    for (let day = 0; day < dayCount; day++) {
        const date = firstDate + day * DAY_MS
        dayStart.push(wallClockToTimestamp(date, 0))
        dayEnd.push(wallClockToTimestamp(date, DAY_MINUTES))
        // Support DST transitions
        const linear = dayEnd[day] - dayStart[day] === DAY_MS
        dayLinear.push(linear)
        const gaps = new Set()
        if (!linear) {
            for (let minute = 0; minute < DAY_MINUTES; minute += QUARTER) {
                const wall = wallClock(wallClockToTimestamp(date, minute))
                if (wall.date !== date || wall.minute !== minute) gaps.add(minute)
            }
        }
        dayGaps.push(gaps)
    }
    const slotExists = (day, minute) => !dayGaps[day].has(minute)
    const timestampAt = (day, minute) => {
        if (minute >= DAY_MINUTES) return dayEnd[day]
        if (dayLinear[day]) return dayStart[day] + minute * 60000
        return wallClockToTimestamp(firstDate + day * DAY_MS, minute)
    }
    const minuteAt = (day, timestamp) => {
        if (timestamp <= dayStart[day]) return 0
        if (timestamp >= dayEnd[day]) return DAY_MINUTES
        if (dayLinear[day]) return Math.floor((timestamp - dayStart[day]) / 60000)
        return wallClock(timestamp).minute
    }
    const dayLabel = (day) => {
        const date = new Date(firstDate + day * DAY_MS)
        return `${weekdayFormat.format(date)} ${dayMonthFormat.format(date)}`
    }

    const key = (day, minute) => `${day}:${minute}`
    const fillRange = (target, start, end) => {
        for (let day = 0; day < dayCount; day++) {
            const from = Math.max(start, dayStart[day])
            const to = Math.min(end, dayEnd[day])
            if (to <= from) continue
            const first = minuteAt(day, from)
            const last = Math.min(DAY_MINUTES, minuteAt(day, to) + (to % 60000 ? 1 : 0))
            for (
                let minute = first - (first % QUARTER);
                minute < last;
                minute += QUARTER
            ) {
                if (slotExists(day, minute)) target.add(key(day, minute))
            }
        }
    }
    const collect = (ranges) => {
        const result = new Set()
        for (const range of ranges || []) {
            const start = Date.parse(range.start)
            const end = Date.parse(range.end)
            if (Number.isNaN(start) || Number.isNaN(end) || end <= start) continue
            fillRange(result, start, end)
        }
        return result
    }

    const constrained = Array.isArray(data.constraints)
    const allowed = constrained ? collect(data.constraints) : null
    const selected = collect(data.availabilities)
    const isAllowed = (day, minute) =>
        slotExists(day, minute) && (!constrained || allowed.has(key(day, minute)))
    const isStale = (day, minute) => constrained && !allowed.has(key(day, minute))

    const storedByDay = Array.from({ length: dayCount }, () => [])
    for (const range of data.availabilities || []) {
        const start = Date.parse(range.start)
        const end = Date.parse(range.end)
        if (Number.isNaN(start) || Number.isNaN(end) || end <= start) continue
        for (let day = 0; day < dayCount; day++) {
            const from = Math.max(start, dayStart[day])
            const to = Math.min(end, dayEnd[day])
            if (to > from) storedByDay[day].push({ start: from, end: to })
        }
    }
    const touched = new Set()

    const resolution = (() => {
        const [hours, minutes] = String(data.resolution || "00:30:00")
            .split(":")
            .map(Number)
        const total = hours * 60 + minutes
        return ROW_HEIGHT[total] ? total : 30
    })()
    const quarters = (minute) => {
        const result = []
        for (let step = minute; step < minute + resolution; step += QUARTER) {
            result.push(step)
        }
        return result
    }

    const slotState = (day, minute) => {
        let open = 0
        let marked = 0
        let stale = false
        for (const step of quarters(minute)) {
            if (isAllowed(day, step)) {
                open++
                if (selected.has(key(day, step))) marked++
            } else if (selected.has(key(day, step))) {
                stale = true
            }
        }
        if (open === 0) return stale ? "stale" : "closed"
        if (marked === 0) return "free"
        return marked === open ? "full" : "partial"
    }
    const slotOpenness = (day, minute) => {
        const open = quarters(minute).filter((step) => isAllowed(day, step)).length
        if (open === 0) return "closed"
        return open === resolution / QUARTER ? "open" : "half"
    }
    const setSlot = (day, minute, marked) => {
        touched.add(day)
        for (const step of quarters(minute)) {
            if (!marked) selected.delete(key(day, step))
            else if (isAllowed(day, step)) selected.add(key(day, step))
        }
    }
    const setDay = (day, marked) => {
        touched.add(day)
        for (let minute = 0; minute < DAY_MINUTES; minute += QUARTER) {
            if (!marked) selected.delete(key(day, minute))
            else if (isAllowed(day, minute)) selected.add(key(day, minute))
        }
    }
    const dayIsOpen = (day) => {
        for (let minute = 0; minute < DAY_MINUTES; minute += QUARTER) {
            if (isAllowed(day, minute)) return true
        }
        return false
    }
    const dayIsFull = (day) => {
        let open = false
        for (let minute = 0; minute < DAY_MINUTES; minute += QUARTER) {
            if (!isAllowed(day, minute)) continue
            open = true
            if (!selected.has(key(day, minute))) return false
        }
        return open
    }
    const hasStale = () => {
        for (const slot of selected) {
            const [day, minute] = slot.split(":").map(Number)
            if (isStale(day, minute)) return true
        }
        return false
    }

    const runs = (day, split) => {
        const result = []
        let current = null
        for (let minute = 0; minute <= DAY_MINUTES; minute += QUARTER) {
            const marked = minute < DAY_MINUTES && selected.has(key(day, minute))
            const stale = marked && split && isStale(day, minute)
            if (current && (!marked || current.stale !== stale)) {
                current.end = minute
                result.push(current)
                current = null
            }
            if (marked && !current) current = { start: minute, stale: stale }
        }
        return result
    }
    const serialize = () => {
        const availabilities = []
        for (let day = 0; day < dayCount; day++) {
            if (!touched.has(day)) {
                for (const range of storedByDay[day]) {
                    availabilities.push({
                        start: new Date(range.start).toISOString(),
                        end: new Date(range.end).toISOString(),
                    })
                }
                continue
            }
            for (const run of runs(day, false)) {
                availabilities.push({
                    start: new Date(timestampAt(day, run.start)).toISOString(),
                    end: new Date(timestampAt(day, run.end)).toISOString(),
                })
            }
        }
        return availabilities
    }

    let showFullDay = false
    const windowRange = () => {
        if (showFullDay) return [0, DAY_MINUTES]
        let start = 8 * 60
        let end = 20 * 60
        if (constrained) {
            start = DAY_MINUTES
            end = 0
            for (const slot of allowed) {
                const minute = Number(slot.split(":")[1])
                start = Math.min(start, minute)
                end = Math.max(end, minute + QUARTER)
            }
            if (start >= end) {
                start = 8 * 60
                end = 20 * 60
            } else {
                start -= 60
                end += 60
            }
        }
        for (const slot of selected) {
            const minute = Number(slot.split(":")[1])
            start = Math.min(start, minute)
            end = Math.max(end, minute + QUARTER)
        }
        start = Math.max(0, Math.floor(start / 60) * 60)
        end = Math.min(DAY_MINUTES, Math.ceil(end / 60) * 60)
        return [start, end]
    }

    const editor = document.createElement("div")
    editor.classList.add("availabilities-editor")
    editor.setAttribute("data-name", element.getAttribute("name"))
    element.insertAdjacentElement("afterend", editor)
    editor.innerHTML = `
        <div class="av-scroll"><div class="av-grid" role="grid"></div></div>
        <div class="av-legend"></div>
        ${
            // With room hours set, every row the toggle reveals is closed and
            // unpaintable, and windowRange() already widens the grid to any
            // existing selection, so the only action left disappears with it.
            constrained
                ? ""
                : `<div class="av-actions"><button type="button" class="btn btn-sm btn-secondary av-full-day" aria-pressed="false">${escapeHtml(strings.show_full_day)}</button></div>`
        }
        <ul class="av-summary sr-only" aria-live="polite"></ul>
    `

    const timezoneHint = document.createElement("span")
    timezoneHint.className = "av-timezone"
    timezoneHint.innerHTML = `<i class="fa fa-globe" aria-hidden="true"></i>${escapeHtml((strings.timezone || "").replace("{tz}", data.event.timezone))}`
    const helpText =
        (element.id && document.getElementById(`${element.id}_helptext`)) ||
        element.closest(".form-group")?.querySelector("small.form-text")
    if (helpText) helpText.append(" ", timezoneHint)
    else editor.append(timezoneHint)

    const grid = editor.querySelector(".av-grid")
    const fieldLabel = element.labels?.[0]
    if (fieldLabel) {
        if (!fieldLabel.id) fieldLabel.id = `${element.id || element.name}_label`
        grid.setAttribute("aria-labelledby", fieldLabel.id)
    }
    const summary = editor.querySelector(".av-summary")
    const legend = editor.querySelector(".av-legend")

    let cells = []
    let dayButtons = []
    let windowStart = 0
    let windowEnd = DAY_MINUTES
    let painting = null
    let hoveredBlock = null

    const setHoveredBlock = (block) => {
        if (block === hoveredBlock) return
        hoveredBlock?.classList.remove("av-block-hover")
        hoveredBlock = block
        hoveredBlock?.classList.add("av-block-hover")
    }
    const hoverBlockAt = (x, y) => {
        for (const block of grid.querySelectorAll(".av-block")) {
            const rect = block.getBoundingClientRect()
            if (x >= rect.left && x < rect.right && y >= rect.top && y < rect.bottom) {
                setHoveredBlock(block)
                return
            }
        }
        setHoveredBlock(null)
    }

    const swatch = (modifier, label) =>
        `<span><i class="av-swatch av-swatch-${modifier}"></i>${escapeHtml(label)}</span>`
    const renderLegend = () => {
        let html = swatch("marked", strings.marked)
        if (constrained) {
            html += swatch("closed", strings.no_rooms)
            if (hasStale()) html += swatch("stale", strings.stale)
        }
        legend.innerHTML = html
    }

    const blockMarkup = (day, run) => {
        const cellMinute =
            windowStart +
            Math.floor((run.start - windowStart) / resolution) * resolution
        if (run.start < windowStart || cellMinute >= windowEnd) return null
        const range = `${clock(run.start)}–${clock(run.end)}`
        const length = (run.end - run.start) / QUARTER
        const height = (length * ROW_HEIGHT[resolution] * QUARTER) / resolution
        const classes = ["av-block"]
        if (run.stale) classes.push("av-block-stale")
        if (height < 20) classes.push("av-block-short")
        else if (height < 32) classes.push("av-block-tight")
        const remove = editable
            ? `<button type="button" class="av-block-remove btn-plain" tabindex="-1" data-day="${day}" data-start="${run.start}" data-end="${run.end}" aria-label="${escapeHtml(
                  [strings.delete, range, dayLabel(day)].filter(Boolean).join(", "),
              )}"></button>`
            : ""
        return {
            cellMinute: cellMinute,
            html: `<div class="${classes.join(" ")}" style="--av-offset: ${(run.start - cellMinute) / QUARTER}; --av-length: ${length}"><span class="av-block-time">${escapeHtml(range)}</span>${remove}</div>`,
        }
    }

    const refreshDay = (day) => {
        const open = dayIsOpen(day)
        const full = dayIsFull(day)
        const button = dayButtons[day]
        if (button) {
            button.disabled = !open
            button.setAttribute("aria-pressed", String(full))
            button.classList.toggle("btn-success", full)
            button.classList.toggle("btn-outline-success", !full)
            button.textContent = open ? strings.all_day : strings.no_rooms
            button.setAttribute("aria-label", `${button.textContent}, ${dayLabel(day)}`)
        }
        const column = cells[day] || {}
        for (const minute of Object.keys(column)) {
            const cell = column[minute]
            const state = slotState(day, Number(minute))
            cell.className = `av-cell av-${slotOpenness(day, Number(minute))}`
            cell.setAttribute("aria-selected", String(state === "full"))
            if (state === "closed") cell.setAttribute("aria-disabled", "true")
            else cell.removeAttribute("aria-disabled")
            cell.innerHTML = ""
        }
        for (const run of runs(day, true)) {
            const block = blockMarkup(day, run)
            if (!block) continue
            const cell = column[block.cellMinute]
            if (cell) cell.insertAdjacentHTML("beforeend", block.html)
        }
        if (!hoveredBlock?.isConnected) hoveredBlock = null
    }

    const afterChange = () => {
        element.setAttribute("value", JSON.stringify({ availabilities: serialize() }))
        if (!painting) {
            summary.innerHTML = Array.from({ length: dayCount }, (_, day) => {
                const ranges = runs(day, false)
                    .map((run) => `${clock(run.start)}–${clock(run.end)}`)
                    .join(", ")
                if (!ranges) return ""
                return `<li><b>${escapeHtml(dayLabel(day))}</b> ${escapeHtml(ranges)}</li>`
            }).join("")
        }
        renderLegend()
    }

    const sizeColumns = () => {
        const head = grid.querySelector(".av-dayhead")
        if (!head) return
        const style = getComputedStyle(head)
        const around =
            parseFloat(style.paddingLeft) +
            parseFloat(style.paddingRight) +
            parseFloat(style.borderRightWidth)
        let widest = 0
        for (const label of grid.querySelectorAll(".av-dayname")) {
            widest = Math.max(widest, label.getBoundingClientRect().width)
        }
        if (widest) {
            editor.style.setProperty("--av-column", `${Math.ceil(widest + around)}px`)
        }
    }

    const render = () => {
        const [start, end] = windowRange()
        windowStart = start
        windowEnd = end
        grid.style.setProperty("--av-days", dayCount)
        grid.style.setProperty("--av-row", `${ROW_HEIGHT[resolution]}px`)
        grid.style.setProperty(
            "--av-quarter",
            `${(ROW_HEIGHT[resolution] * QUARTER) / resolution}px`,
        )
        let html = `<div class="av-row av-row-head" role="row"><div class="av-corner" role="columnheader"></div>`
        for (let day = 0; day < dayCount; day++) {
            const date = new Date(firstDate + day * DAY_MS)
            html += `<div class="av-dayhead" role="columnheader"><span class="av-dayname"><b>${escapeHtml(weekdayFormat.format(date))}</b>${escapeHtml(dayMonthFormat.format(date))}</span>`
            if (editable) {
                html += `<button type="button" class="btn btn-sm av-day-all" data-day="${day}"></button>`
            }
            html += "</div>"
        }
        html += "</div>"
        for (let minute = windowStart; minute < windowEnd; minute += resolution) {
            const onHour = minute % 60 === 0
            html += `<div class="av-row${onHour ? " av-row-hour" : ""}" role="row"><div class="av-time" role="rowheader">${onHour ? clock(minute) : ""}</div>`
            for (let day = 0; day < dayCount; day++) {
                const reason =
                    constrained && slotOpenness(day, minute) === "closed"
                        ? strings.no_rooms
                        : ""
                const label = `${dayLabel(day)} ${clock(minute)}–${clock(minute + resolution)}${reason ? `, ${reason}` : ""}`
                html += `<div class="av-cell" role="gridcell" tabindex="-1" data-day="${day}" data-minute="${minute}" aria-label="${escapeHtml(label)}"></div>`
            }
            html += "</div>"
        }
        grid.innerHTML = html
        cells = []
        dayButtons = [...grid.querySelectorAll(".av-day-all")]
        for (const cell of grid.querySelectorAll(".av-cell")) {
            const day = Number(cell.dataset.day)
            cells[day] = cells[day] || {}
            cells[day][Number(cell.dataset.minute)] = cell
        }
        for (let day = 0; day < dayCount; day++) refreshDay(day)
        const first =
            grid.querySelector(".av-cell:not(.av-closed)") ||
            grid.querySelector(".av-cell")
        if (first) first.tabIndex = 0
        sizeColumns()
        afterChange()
    }

    const cellFromPoint = (x, y) => document.elementFromPoint(x, y)?.closest(".av-cell")
    const cellState = (cell) =>
        slotState(Number(cell.dataset.day), Number(cell.dataset.minute))
    const paintTo = (cell) => {
        if (!cell || !painting) return
        const day = Number(cell.dataset.day)
        const minute = Number(cell.dataset.minute)
        const firstDay = Math.min(day, painting.day)
        const lastDay = Math.max(day, painting.day)
        const firstMinute = Math.min(minute, painting.minute)
        const lastMinute = Math.max(minute, painting.minute)
        selected.clear()
        for (const slot of painting.snapshot) selected.add(slot)
        const affected = painting.days
        painting.days = new Set()
        for (let target = firstDay; target <= lastDay; target++) {
            for (let step = firstMinute; step <= lastMinute; step += resolution) {
                setSlot(target, step, painting.marked)
            }
            painting.days.add(target)
            affected.add(target)
        }
        for (const target of affected) refreshDay(target)
        afterChange()
    }
    const startPaint = (cell) => {
        const state = cellState(cell)
        if (state === "closed") return
        painting = {
            marked: state === "free" || state === "partial",
            day: Number(cell.dataset.day),
            minute: Number(cell.dataset.minute),
            snapshot: new Set(selected),
            days: new Set(),
        }
        grid.classList.add("av-painting")
        paintTo(cell)
    }
    const endPaint = () => {
        if (!painting) return
        painting = null
        grid.classList.remove("av-painting")
        afterChange()
    }

    if (editable) {
        grid.addEventListener("pointerdown", (event) => {
            if (event.pointerType === "touch" || event.button !== 0) return
            if (event.target.closest(".av-block-remove")) return
            const cell = event.target.closest(".av-cell")
            if (!cell || cellState(cell) === "closed") return
            event.preventDefault()
            grid.setPointerCapture(event.pointerId)
            startPaint(cell)
        })
        grid.addEventListener("pointermove", (event) => {
            if (event.pointerType === "touch") return
            if (painting) {
                paintTo(cellFromPoint(event.clientX, event.clientY))
                return
            }
            hoverBlockAt(event.clientX, event.clientY)
        })
        grid.addEventListener("pointerleave", () => setHoveredBlock(null))
        grid.addEventListener("pointerup", endPaint)
        grid.addEventListener("pointercancel", endPaint)
        grid.addEventListener("contextmenu", (event) => {
            if (event.target.closest(".av-cell")) event.preventDefault()
        })

        let touchTimer = null
        let touchOrigin = null
        grid.addEventListener(
            "touchstart",
            (event) => {
                if (event.touches.length !== 1) return
                if (event.target.closest(".av-block-remove")) return
                const cell = event.target.closest(".av-cell")
                if (!cell) return
                const touch = event.touches[0]
                touchOrigin = { x: touch.clientX, y: touch.clientY, cell: cell }
                touchTimer = setTimeout(() => {
                    touchTimer = null
                    if (cellState(cell) !== "closed") {
                        startPaint(cell)
                        navigator.vibrate?.(15)
                    }
                }, 280)
            },
            { passive: true },
        )
        grid.addEventListener(
            "touchmove",
            (event) => {
                const touch = event.touches[0]
                if (painting) {
                    event.preventDefault()
                    paintTo(cellFromPoint(touch.clientX, touch.clientY))
                    return
                }
                if (
                    touchTimer &&
                    Math.hypot(
                        touch.clientX - touchOrigin.x,
                        touch.clientY - touchOrigin.y,
                    ) > 8
                ) {
                    clearTimeout(touchTimer)
                    touchTimer = null
                }
            },
            { passive: false },
        )
        const finishTouch = (event) => {
            if (touchTimer) {
                clearTimeout(touchTimer)
                touchTimer = null
                if (
                    event.type === "touchend" &&
                    cellState(touchOrigin.cell) !== "closed"
                ) {
                    event.preventDefault()
                    startPaint(touchOrigin.cell)
                }
            }
            endPaint()
        }
        grid.addEventListener("touchend", finishTouch)
        grid.addEventListener("touchcancel", finishTouch)

        grid.addEventListener("click", (event) => {
            const remove = event.target.closest(".av-block-remove")
            if (remove) {
                const day = Number(remove.dataset.day)
                touched.add(day)
                for (
                    let minute = Number(remove.dataset.start);
                    minute < Number(remove.dataset.end);
                    minute += QUARTER
                ) {
                    selected.delete(key(day, minute))
                }
                refreshDay(day)
                afterChange()
                return
            }
            const button = event.target.closest(".av-day-all")
            if (!button) return
            const day = Number(button.dataset.day)
            setDay(day, !dayIsFull(day))
            render()
            dayButtons[day]?.focus()
        })
    }

    grid.addEventListener("keydown", (event) => {
        const cell = event.target.closest(".av-cell")
        if (!cell) return
        const day = Number(cell.dataset.day)
        const minute = Number(cell.dataset.minute)
        let targetDay = day
        let targetMinute = minute
        switch (event.key) {
            case "ArrowUp":
                targetMinute = minute - resolution
                break
            case "ArrowDown":
                targetMinute = minute + resolution
                break
            case "ArrowLeft":
                targetDay = day - 1
                break
            case "ArrowRight":
                targetDay = day + 1
                break
            case "Home":
                targetMinute = windowStart
                break
            case "End":
                targetMinute = windowEnd - resolution
                break
            case " ":
            case "Enter": {
                event.preventDefault()
                if (!editable) return
                const state = slotState(day, minute)
                if (state === "closed") return
                setSlot(day, minute, state === "free" || state === "partial")
                refreshDay(day)
                afterChange()
                return
            }
            default:
                return
        }
        event.preventDefault()
        const target = cells[targetDay]?.[targetMinute]
        if (!target) return
        cell.tabIndex = -1
        target.tabIndex = 0
        target.focus()
    })

    const fullDayButton = editor.querySelector(".av-full-day")
    fullDayButton?.addEventListener("click", () => {
        showFullDay = !showFullDay
        fullDayButton.setAttribute("aria-pressed", String(showFullDay))
        render()
    })

    render()
    document.fonts?.ready?.then(sizeColumns)
}

const initAvailabilitiesIn = (container) => {
    if (!container?.querySelectorAll) return
    if (container.matches?.("input.availabilities-editor-data"))
        initAvailabilities(container)
    container
        .querySelectorAll("input.availabilities-editor-data")
        .forEach((element) => initAvailabilities(element))
}

onReady(() => {
    initAvailabilitiesIn(document)
})

document.addEventListener("htmx:load", (event) => {
    initAvailabilitiesIn(event.detail.elt)
})
