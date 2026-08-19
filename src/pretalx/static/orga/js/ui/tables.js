// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const refreshTableContent = (tableName, url, options = {}) => {
  const tableContainer = document.querySelector(`#table-content-${tableName}`)
  if (!tableContainer || typeof htmx === "undefined") {
    window.location.reload()
    return
  }

  htmx.ajax("GET", url, {
    target: `#table-content-${tableName}`,
    swap: "innerHTML",
    source: tableContainer,
  })
}

const setupTableHtmx = (tableContent) => {
  const tableName = tableContent.dataset.tableName
  if (!tableName) return

  const targetSelector = `#table-content-${tableName}`

  tableContent.querySelectorAll(".table-sort-link").forEach((link) => {
    link.setAttribute("hx-get", link.href)
    link.setAttribute("hx-target", targetSelector)
    link.setAttribute("hx-swap", "innerHTML")
    link.setAttribute("hx-push-url", "true")
    link.setAttribute("hx-indicator", targetSelector)
  })

  tableContent.querySelectorAll(".table-page-link").forEach((link) => {
    link.setAttribute("hx-get", link.href)
    link.setAttribute("hx-target", targetSelector)
    link.setAttribute("hx-swap", "innerHTML")
    link.setAttribute("hx-push-url", "true")
    link.setAttribute("hx-indicator", targetSelector)
    link.dataset.scrollToTable = "true"
  })

  if (typeof htmx !== "undefined") {
    htmx.process(tableContent)
  }
}

const setupColumnPicker = (root) => {
  const picker = root.querySelector(".column-picker")
  const shown = picker.querySelector(".column-picker-shown")
  const pool = picker.querySelector(".column-picker-hidden")
  const rowTemplate = picker.querySelector(".column-row-template")
  const chipTemplate = picker.querySelector(".column-chip-template")

  const entries = new Map()
  const register = (element, label) =>
    entries.set(element.dataset.column, {
      name: element.dataset.column,
      label,
      order: Number(element.dataset.order),
    })
  shown
    .querySelectorAll(".column-row")
    .forEach((row) =>
      register(row, row.querySelector(".column-row-label").textContent),
    )
  pool
    .querySelectorAll(".column-chip")
    .forEach((chip) =>
      register(chip, chip.querySelector(".column-chip-label").textContent),
    )

  const notifyChange = () =>
    root.dispatchEvent(new CustomEvent("tableoptions:change"))

  const build = (template, entry, labelSelector) => {
    const element = template.content.firstElementChild.cloneNode(true)
    element.dataset.column = entry.name
    element.dataset.order = entry.order
    element.querySelector(labelSelector).textContent = entry.label
    return element
  }
  const makeRow = (entry) => {
    const row = build(rowTemplate, entry, ".column-row-label")
    row.setAttribute("dragsort-id", entry.name)
    return row
  }
  const makeChip = (entry) => build(chipTemplate, entry, ".column-chip-label")

  const getColumns = () =>
    Array.from(shown.children).map((row) => row.dataset.column)

  const renderPool = (selected) =>
    pool.replaceChildren(
      ...Array.from(entries.values())
        .filter((entry) => !selected.includes(entry.name))
        .sort((a, b) => a.order - b.order)
        .map(makeChip),
    )

  const setColumns = (columns) => {
    const selected = columns.filter((name) => entries.has(name))
    shown.replaceChildren(...selected.map((name) => makeRow(entries.get(name))))
    renderPool(selected)
    initDragsort(shown)
  }

  const hideColumn = (row) => {
    const focusTarget = row.nextElementSibling || row.previousElementSibling
    row.remove()
    renderPool(getColumns())
    focusTarget?.focus()
    notifyChange()
  }

  const showColumn = (chip) => {
    const row = makeRow(entries.get(chip.dataset.column))
    shown.appendChild(row)
    chip.remove()
    initDragsort(shown)
    row.focus()
    notifyChange()
  }

  picker.addEventListener("click", (event) => {
    const chip = event.target.closest(".column-chip")
    if (chip) {
      showColumn(chip)
      return
    }
    const remove = event.target.closest(".column-remove")
    if (remove) hideColumn(remove.closest(".column-row"))
  })

  shown.addEventListener("keydown", (event) => {
    const row = event.target
    if (!row.classList?.contains("column-row")) return
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault()
      hideColumn(row)
      return
    }
    if (!event.altKey) return
    const offset =
      event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0
    if (!offset) return
    event.preventDefault()
    moveByKeyboard(row, row, offset)
  })
  shown.addEventListener("dragsort:reorder", notifyChange)

  return { getColumns, setColumns }
}

const setupSortSection = (root) => {
  const section = root.querySelector(".sort-section")
  if (!section) return { getOrdering: () => [], setOrdering: () => {} }

  const levels = section.querySelector(".sort-levels")
  const template = section.querySelector(".sort-level-template")
  const addButton = section.querySelector(".add-sort-level")
  const maxLevels = Number(section.dataset.maxLevels)
  const columnCount = template.content.querySelectorAll(
    ".sort-column option[value]:not([value=''])",
  ).length

  const notifyChange = () =>
    root.dispatchEvent(new CustomEvent("tableoptions:change"))
  const getSelects = () => Array.from(levels.querySelectorAll(".sort-column"))
  const syncLevels = () => {
    const used = new Set(getSelects().map((select) => select.value))
    used.delete("")
    getSelects().forEach((select) => {
      Array.from(select.options).forEach((option) => {
        const taken =
          Boolean(option.value) &&
          option.value !== select.value &&
          used.has(option.value)
        option.hidden = taken
        option.disabled = taken
      })
    })
    addButton.classList.toggle(
      "d-none",
      levels.children.length >= maxLevels || used.size >= columnCount,
    )
  }
  const syncNumeric = (level) => {
    const option = level.querySelector(".sort-column").selectedOptions[0]
    level.toggleAttribute("data-numeric", Boolean(option?.dataset.numeric))
  }
  const setDirection = (level, direction) =>
    level
      .querySelectorAll(".sort-direction-btn")
      .forEach((button) =>
        button.setAttribute(
          "aria-pressed",
          String(button.dataset.direction === direction),
        ),
      )

  const addLevel = (column = "", direction = "asc") => {
    const level = template.content.firstElementChild.cloneNode(true)
    level.querySelector(".sort-column").value = column
    setDirection(level, direction)
    syncNumeric(level)
    levels.appendChild(level)
    syncLevels()
    return level
  }

  const getOrdering = () => {
    const ordering = []
    const seen = new Set()
    Array.from(levels.children).forEach((level) => {
      const column = level.querySelector(".sort-column").value
      if (!column || seen.has(column)) return
      seen.add(column)
      const descending =
        level
          .querySelector(".sort-direction-btn[data-direction='desc']")
          .getAttribute("aria-pressed") === "true"
      ordering.push(descending ? `-${column}` : column)
    })
    return ordering
  }

  const setOrdering = (ordering) => {
    levels.replaceChildren()
    ordering.forEach((field) =>
      addLevel(field.replace(/^-/, ""), field.startsWith("-") ? "desc" : "asc"),
    )
    syncLevels()
  }

  section.addEventListener("click", (event) => {
    const direction = event.target.closest(".sort-direction-btn")
    if (direction) {
      setDirection(direction.closest(".sort-level"), direction.dataset.direction)
      notifyChange()
      return
    }
    const remove = event.target.closest(".sort-remove")
    if (remove) {
      remove.closest(".sort-level").remove()
      syncLevels()
      notifyChange()
    }
  })
  section.addEventListener("change", (event) => {
    const select = event.target.closest(".sort-column")
    if (!select) return
    syncNumeric(select.closest(".sort-level"))
    syncLevels()
    notifyChange()
  })
  addButton.addEventListener("click", () =>
    addLevel().querySelector(".sort-column").focus(),
  )

  Array.from(levels.children).forEach(syncNumeric)
  syncLevels()
  return { getOrdering, setOrdering }
}

const bindColumnGuard = (form, picker, button) => {
  const syncDisabled = () => {
    button.disabled = picker.getColumns().length === 0
  }
  syncDisabled()
  form.addEventListener("tableoptions:change", syncDisabled)
  return syncDisabled
}

const getEventSlug = () => {
  const pathParts = window.location.pathname.split("/")
  const eventIndex = pathParts.indexOf("event")
  if (eventIndex !== -1 && pathParts.length > eventIndex + 1) {
    return pathParts[eventIndex + 1]
  }
  return null
}

const savePreferences = async (payload) => {
  const eventSlug = getEventSlug()
  if (!eventSlug) return false
  const response = await fetch(`/orga/event/${eventSlug}/preferences/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("pretalx_csrftoken"),
    },
    body: JSON.stringify(payload),
  })
  return response.ok
}

const setupPreferenceModal = (form) => {
  if (form.dataset.tableOptionsBound) return
  form.dataset.tableOptionsBound = "1"

  const tableName = form.dataset.tableName
  const dialog = form.closest("dialog")
  const picker = setupColumnPicker(form)
  const sort = setupSortSection(form)
  const defaultColumns = JSON.parse(form.dataset.defaultColumns)

  let baseline = { columns: picker.getColumns(), ordering: sort.getOrdering() }
  let resetPending = false

  const applyState = (state) => {
    picker.setColumns(state.columns)
    sort.setOrdering(state.ordering)
  }

  const saveButton = form.querySelector(".save-preferences")
  const syncDisabled = bindColumnGuard(form, picker, saveButton)

  form.addEventListener("tableoptions:change", () => {
    resetPending = false
  })
  dialog.addEventListener("close", () => {
    applyState(baseline)
    syncDisabled()
    resetPending = false
  })

  const refreshTable = () => {
    // Remove sort/page params - backend will set HX-Push-Url with clean URL
    const url = new URL(window.location.href)
    url.searchParams.delete("sort")
    url.searchParams.delete("page")
    refreshTableContent(tableName, url.toString())
  }

  saveButton.addEventListener("click", async () => {
    const columns = picker.getColumns()
    if (columns.length === 0) return

    const ordering = sort.getOrdering()
    const payload = resetPending
      ? { table_name: tableName, reset: true }
      : { table_name: tableName, columns: columns, ordering: ordering }
    const restoreButton = setButtonLoading(saveButton)

    try {
      if (await savePreferences(payload)) {
        baseline = { columns: columns, ordering: ordering }
        dialog.close()
        restoreButton()
        refreshTable()
      } else {
        console.error("Failed to save table preferences")
        alert("Failed to save preferences. Please try again.")
        restoreButton()
      }
    } catch (error) {
      console.error("Error saving table preferences:", error)
      alert("An error occurred. Please try again.")
      restoreButton()
    }
  })

  const resetButton = form.querySelector(".reset-preferences")
  resetButton.addEventListener("click", () => {
    applyState({ columns: defaultColumns, ordering: [] })
    syncDisabled()
    resetPending = true
  })
}

const handleTablePreferences = () => {
  document
    .querySelectorAll(".table-preferences-form")
    .forEach((form) => setupPreferenceModal(form))
}

const handleTableHtmx = () => {
  document
    .querySelectorAll(".table-content")
    .forEach((tableContent) => setupTableHtmx(tableContent))
}

const renderPrintOverlay = (html) => {
  const overlay = document.createElement("div")
  overlay.id = "table-print-overlay"
  overlay.innerHTML = html
  overlay
    .querySelectorAll(
      ".table-toolbar, .table-loading-overlay, dialog, nav.text-center",
    )
    .forEach((el) => el.remove())
  document.body.appendChild(overlay)
  document.documentElement.classList.add("printing-table")

  const cleanup = () => {
    overlay.remove()
    document.documentElement.classList.remove("printing-table")
    window.removeEventListener("afterprint", cleanup)
  }
  window.addEventListener("afterprint", cleanup)
  window.print()
}

const printCurrentTable = (tableName) => {
  // Called when there is no preferences form, so we just print the current table.
  const tableContent = document.querySelector(`#table-content-${tableName}`)
  if (!tableContent) return
  renderPrintOverlay(tableContent.innerHTML)
}

const fetchTableForPrint = async (tableName, columns) => {
  const url = new URL(window.location.href)
  url.searchParams.delete("print")
  columns.forEach((c) => url.searchParams.append("print", c))
  url.searchParams.delete("page")
  url.searchParams.set("paginate", "0")
  const response = await fetch(url.toString(), {
    headers: {
      "HX-Request": "true",
      "HX-Target": `table-content-${tableName}`,
      "HX-Pretalx-Print": "1",
    },
  })
  if (!response.ok) {
    throw new Error(`Failed to load print table (${response.status}).`)
  }
  return response.text()
}

const setupPrintModal = (form) => {
  if (form.dataset.tableOptionsBound) return
  form.dataset.tableOptionsBound = "1"

  const tableName = form.dataset.tableName
  const dialog = form.closest("dialog")
  const picker = setupColumnPicker(form)
  const printButton = form.querySelector(".print-now")
  const baseline = picker.getColumns()

  const syncDisabled = bindColumnGuard(form, picker, printButton)
  dialog.addEventListener("close", () => {
    picker.setColumns(baseline)
    syncDisabled()
  })

  printButton.addEventListener("click", async () => {
    const columns = picker.getColumns()
    if (columns.length === 0) return

    const restoreButton = setButtonLoading(printButton)
    try {
      const html = await fetchTableForPrint(tableName, columns)
      dialog.close()
      restoreButton()
      renderPrintOverlay(html)
    } catch (error) {
      console.error("Error preparing print:", error)
      alert("Failed to prepare print. Please try again.")
      restoreButton()
    }
  })
}

const setupPrintButton = (button) => {
  if (button.dataset.printBound) return
  button.dataset.printBound = "1"
  if (button.dataset.dialogTarget) return
  button.addEventListener("click", () =>
    printCurrentTable(button.dataset.tableName),
  )
}

const handleTablePrint = (root = document) => {
  root.querySelectorAll(".table-print-btn").forEach(setupPrintButton)
  root.querySelectorAll(".table-print-form").forEach(setupPrintModal)
}

// Track whether we should scroll after swap (set before swap, used after)
let pendingScrollTarget = null

document.addEventListener("htmx:beforeRequest", (event) => {
  const trigger = event.detail.elt
  if (trigger?.dataset?.scrollToTable) {
    pendingScrollTarget = event.detail.target
  }
})

document.addEventListener("htmx:afterSwap", (event) => {
  // History restores swap the whole body and carry no target element.
  const target = event.detail.target
  if (!target?.classList) return
  const content = target.classList.contains("table-content") ? target : null
  if (content) {
    setupTableHtmx(content)
    handleTablePrint(content)

    const form = content.querySelector(".table-preferences-form")
    if (form) {
      setupPreferenceModal(form)
      setupModals(content)
    }

    if (pendingScrollTarget === target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" })
      pendingScrollTarget = null
    }
  }
})

document.addEventListener("htmx:responseError", (event) => {
  const target = event.detail.target
  if (
    target?.classList.contains("table-content") ||
    target?.classList.contains("table-wrapper")
  ) {
    target.classList.remove("htmx-request")
    target.querySelector?.(".table-content")?.classList.remove("htmx-request")
    pendingScrollTarget = null

    const status = event.detail.xhr?.status
    const message =
      status === 0
        ? "Network error. Please check your connection."
        : `Failed to load table (${status}). Please try again.`
    alert(message)
  }
})

onReady(handleTablePreferences)
onReady(handleTableHtmx)
onReady(() => handleTablePrint())
