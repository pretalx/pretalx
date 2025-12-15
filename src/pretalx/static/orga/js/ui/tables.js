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

const setupPreferenceModal = (form) => {
  const tableName = form.dataset.tableName
  const dialog = form.closest("dialog")
  const availableSelect = form.querySelector(".available-columns")
  const selectedSelect = form.querySelector(".selected-columns")

  const moveOptions = (from, to, selected = false) => {
    const options = Array.from(from.selectedOptions)
    if (options.length === 0) return

    options.forEach((option) => {
      const newOption = option.cloneNode(true)
      newOption.selected = selected
      to.appendChild(newOption)
      option.remove()
    })

    if (!to.classList.contains("selected-columns")) {
      sortSelectOptions(to)
    }
  }

  const sortSelectOptions = (select) => {
    const options = Array.from(select.options)
    options.sort((a, b) => a.text.localeCompare(b.text))
    select.innerHTML = ""
    options.forEach((option) => select.appendChild(option))
  }

  const moveOption = (select, direction) => {
    const options = Array.from(select.selectedOptions)
    if (options.length === 0) return

    if (direction === "up") {
      options.forEach((option) => {
        const prev = option.previousElementSibling
        if (prev) {
          select.insertBefore(option, prev)
        }
      })
    } else {
      options.reverse().forEach((option) => {
        const next = option.nextElementSibling
        if (next) {
          select.insertBefore(next, option)
        }
      })
    }
  }

  form.querySelector(".add-columns")?.addEventListener("click", () => {
    moveOptions(availableSelect, selectedSelect, true)
  })
  form.querySelector(".remove-columns")?.addEventListener("click", () => {
    moveOptions(selectedSelect, availableSelect)
  })
  form.querySelector(".move-up")?.addEventListener("click", () => {
    moveOption(selectedSelect, "up")
  })
  form.querySelector(".move-down")?.addEventListener("click", () => {
    moveOption(selectedSelect, "down")
  })
  availableSelect?.addEventListener("dblclick", (e) => {
    if (e.target.tagName === "OPTION") {
      e.target.selected = true
      moveOptions(availableSelect, selectedSelect, true)
    }
  })
  selectedSelect?.addEventListener("dblclick", (e) => {
    if (e.target.tagName === "OPTION") {
      e.target.selected = true
      moveOptions(selectedSelect, availableSelect)
    }
  })

  const getEventSlug = () => {
    const pathParts = window.location.pathname.split("/")
    const eventIndex = pathParts.indexOf("event")
    if (eventIndex !== -1 && pathParts.length > eventIndex + 1) {
      return pathParts[eventIndex + 1]
    }
    return null
  }

  const sortColumn1 = form.querySelector("[name='sort_column_1']")
  const sortDirection1 = form.querySelector("[name='sort_direction_1']")
  const sortColumn2 = form.querySelector("[name='sort_column_2']")
  const sortDirection2 = form.querySelector("[name='sort_direction_2']")

  const getOrdering = () => {
    const ordering = []
    if (sortColumn1?.value) {
      const dir1 = sortDirection1?.value === "desc" ? "-" : ""
      ordering.push(dir1 + sortColumn1.value)
    }
    if (sortColumn2?.value && sortColumn2.value !== sortColumn1?.value) {
      const dir2 = sortDirection2?.value === "desc" ? "-" : ""
      ordering.push(dir2 + sortColumn2.value)
    }
    return ordering
  }

  const refreshTable = () => {
    // Remove sort/page params - backend will set HX-Push-Url with clean URL
    const url = new URL(window.location.href)
    url.searchParams.delete("sort")
    url.searchParams.delete("page")
    refreshTableContent(tableName, url.toString())
  }

  const saveButton = form.querySelector(".save-preferences")
  saveButton?.addEventListener("click", async () => {
    Array.from(selectedSelect.options).forEach((option) => {
      option.selected = true
    })

    const columns = Array.from(selectedSelect.options).map((opt) => opt.value)
    const ordering = getOrdering()
    const restoreButton = setButtonLoading(saveButton)

    try {
      const eventSlug = getEventSlug()
      if (!eventSlug) {
        console.error("Could not determine event slug from URL")
        alert("An error occurred. Please try again.")
        restoreButton()
        return
      }
      const response = await fetch(`/orga/event/${eventSlug}/preferences/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("pretalx_csrftoken"),
        },
        body: JSON.stringify({
          table_name: tableName,
          columns: columns,
          ordering: ordering,
        }),
      })

      if (response.ok) {
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
  resetButton?.addEventListener("click", async () => {
    if (!confirm("Reset table preferences to defaults?")) {
      return
    }

    const restoreButton = setButtonLoading(resetButton)

    try {
      const eventSlug = getEventSlug()
      if (!eventSlug) {
        console.error("Could not determine event slug from URL")
        alert("An error occurred. Please try again.")
        restoreButton()
        return
      }
      const response = await fetch(`/orga/event/${eventSlug}/preferences/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("pretalx_csrftoken"),
        },
        body: JSON.stringify({
          table_name: tableName,
          reset: true,
        }),
      })

      if (response.ok) {
        dialog.close()
        restoreButton()
        refreshTable()
      } else {
        console.error("Failed to reset table preferences")
        alert("Failed to reset preferences. Please try again.")
        restoreButton()
      }
    } catch (error) {
      console.error("Error resetting table preferences:", error)
      alert("An error occurred. Please try again.")
      restoreButton()
    }
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

// Track whether we should scroll after swap (set before swap, used after)
let pendingScrollTarget = null

document.addEventListener("htmx:beforeRequest", (event) => {
  const trigger = event.detail.elt
  if (trigger?.dataset?.scrollToTable) {
    pendingScrollTarget = event.detail.target
  }
})

// Re-initialize HTMX attributes and preference modals after table content is swapped
document.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail.target
  if (target.classList.contains("table-content")) {
    setupTableHtmx(target)

    const form = target.querySelector(".table-preferences-form")
    if (form) {
      setupPreferenceModal(form)
      setupModals(target)
    }

    if (pendingScrollTarget === target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" })
      pendingScrollTarget = null
    }
  }
})

document.addEventListener("htmx:responseError", (event) => {
  const target = event.detail.target
  if (target?.classList.contains("table-content")) {
    target.classList.remove("htmx-request")
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
