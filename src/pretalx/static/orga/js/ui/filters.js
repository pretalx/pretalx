// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const filterUrl = (form) => {
  // Rewrite only queryparams that are part of the filter bar
  const params = new URLSearchParams(window.location.search)
  params.delete("page")
  for (const name of (form.dataset.params || "").split(",")) {
    if (name) params.delete(name)
  }
  for (const element of form.elements) {
    if (!element.name || element.disabled) continue
    if (element.type === "checkbox" || element.type === "radio") {
      if (!element.checked) continue
    }
    if (element.multiple) {
      for (const option of element.selectedOptions) {
        if (option.value && option.value !== element.dataset.emptyValue) {
          params.append(element.name, option.value)
        }
      }
      continue
    }
    const value = element.value
    if (value === "" || value === element.dataset.emptyValue) continue
    params.append(element.name, value)
  }
  const query = params.toString()
  return `${window.location.pathname}${query ? `?${query}` : ""}`
}

const applyFilters = (tableName, url) => {
  // Applyin filters re-renders the table AND the filter pills AND the popover
  // footer, but not the popover itself, because doing that while it's open
  // would introduce so much jank.
  const content = document.querySelector(`#table-content-${tableName}`)
  if (!content || typeof htmx === "undefined") {
    window.location.href = url
    return
  }
  htmx.ajax("GET", url, { target: content, source: content })
}

document.addEventListener("htmx:oobBeforeSwap", (event) => {
  // Filter changes made inside the open popover must not re-render it (jank);
  // changes from outside must re-render it (to update values).
  const target = event.detail.target
  if (!(target?.id || "").startsWith("filter-popover-body-")) return
  if (target.closest(".filter-popover")?.matches(":popover-open")) {
    event.preventDefault()
  }
})

document.addEventListener("htmx:oobAfterSwap", (event) => {
  const id = event.detail.target?.id || ""
  if (id.startsWith("filter-popover-body-")) {
    const popover = event.detail.target.closest(".filter-popover")
    if (popover) delete popover.dataset.selectsReady
    return
  }
  if (!id.startsWith("filter-status-")) return
  const tableName = id.slice("filter-status-".length)
  const root = document.querySelector(
    `.table-filter-controls[data-table-name="${tableName}"]`,
  )
  const popover = root?.querySelector(".filter-popover")
  if (root && popover) anchorPopover(root, popover)
})

const applyForm = (form) => applyFilters(form.dataset.tableName, filterUrl(form))

const anchorPopover = (root, popover) => {
  const facet = popover.dataset.activeFacet || ""
  const trigger =
    root.querySelector(`[popovertarget][data-facet="${CSS.escape(facet)}"]`) ||
    root.querySelector(".filter-pill-add")
  root.querySelectorAll("[popovertarget]").forEach((other) => {
    other.style.anchorName = ""
  })
  if (trigger) trigger.style.anchorName = "--filter-anchor"
}

const pinDropdown = (container) => {
  // Rendering the choices dropdown inside an already-scrolling popover is
  // tricky. Sigh. We pin it to the viewport to avoid container resizing hell.
  const list = container.querySelector(".choices__list--dropdown")
  const anchor = container.querySelector(".choices__inner")
  if (!list || !anchor) return
  const rect = anchor.getBoundingClientRect()
  const below = window.innerHeight - rect.bottom
  const available = Math.max(below, rect.top) - 16
  Object.assign(list.style, {
    position: "fixed",
    left: `${rect.left}px`,
    width: `${rect.width}px`,
  })
  const inner = list.querySelector(".choices__list") || list
  const dropdown_min_height = 180
  const dropdown_max_height = 340
  inner.style.maxHeight = `${Math.max(dropdown_min_height, Math.min(dropdown_max_height, available))}px`
  inner.style.overflowY = "auto"
  if (below < dropdown_min_height && rect.top > below) {
    list.style.top = "auto"
    list.style.bottom = `${window.innerHeight - rect.top}px`
  } else {
    list.style.bottom = "auto"
    list.style.top = `${rect.bottom}px`
  }
}

const unpinDropdown = (container) => {
  const list = container.querySelector(".choices__list--dropdown")
  if (!list) return
  for (const property of ["position", "left", "width", "top", "bottom"]) {
    list.style[property] = ""
  }
  const inner = list.querySelector(".choices__list")
  if (inner) {
    inner.style.maxHeight = ""
    inner.style.overflowY = ""
  }
}

const setupPinnedDropdowns = (popover) => {
  let open = null

  popover.addEventListener(
    "keydown",
    (event) => {
      if (event.key !== "Escape") return
      if (popover.querySelector(".choices.is-open")) event.preventDefault()
    },
    true,
  )
  popover.addEventListener("showDropdown", (event) => {
    open = event.target.closest(".choices")
    if (open) pinDropdown(open)
  })
  popover.addEventListener("hideDropdown", (event) => {
    const container = event.target.closest(".choices")
    if (container) unpinDropdown(container)
    open = null
  })
  popover
    .querySelector(".filter-popover-body")
    ?.addEventListener("scroll", () => {
      if (open) pinDropdown(open)
    })
}

const setupFilterForm = (root) => {
  if (root.dataset.filtersReady) return
  root.dataset.filtersReady = "true"
  const tableName = root.dataset.tableName
  const form = document.getElementById(`filter-form-${tableName}`)
  if (!form) return
  form.dataset.tableName = tableName
  const popover = root.querySelector(".filter-popover")

  form.addEventListener("submit", (event) => {
    event.preventDefault()
    applyForm(form)
  })

  root.addEventListener("change", (event) => {
    const target = event.target
    if (
      (target.type === "search" || target.type === "text") &&
      target.dataset.applyOnChange === undefined
    ) {
      return
    }
    applyForm(form)
  })

  root.addEventListener("click", (event) => {
    const trigger = event.target.closest("[popovertarget]")
    if (trigger && popover) {
      root.querySelectorAll("[popovertarget]").forEach((other) => {
        other.style.anchorName = ""
      })
      popover.dataset.activeFacet = trigger.dataset.facet || ""
      anchorPopover(root, popover)
      return
    }
    const link = event.target.closest(".filter-apply-link")
    if (link) {
      event.preventDefault()
      const url = new URL(link.href, window.location.href)
      applyFilters(tableName, `${url.pathname}${url.search}`)
    }
  })

  popover?.addEventListener("toggle", (event) => {
    const open = event.newState === "open"
    root.querySelectorAll("[popovertarget]").forEach((trigger) => {
      trigger.classList.toggle(
        "filter-pill-open",
        open && (trigger.dataset.facet || "") === (popover.dataset.activeFacet || ""),
      )
    })
    if (!open) return
    if (!popover.dataset.selectsReady) {
      popover.dataset.selectsReady = "true"
      window.initEnhancedSelects?.(popover, { deferred: true })
    }
    const facet = popover.dataset.activeFacet
    const block = facet
      ? popover.querySelector(`.filter-block[data-facet="${CSS.escape(facet)}"]`)
      : null
    if (block) {
      block.scrollIntoView({ block: "start" })
      block.querySelector("select, input:not([type=hidden])")?.focus()
    }
  })

  if (popover) setupPinnedDropdowns(popover)
}

const handleFilters = (scope = document) => {
  scope.querySelectorAll(".table-filter-controls").forEach(setupFilterForm)
}

onReady(() => handleFilters())
