// Loads the pretix ticket table after the page shell has rendered, and shows a
// spinner on buttons whose request waits for pretix.

const SPINNER_CLASS = "fa fa-circle-o-notch fa-spin"

const showBusy = (el) => {
  if (!el || el.dataset.busy) return
  el.dataset.busy = "1"
  el.classList.add("disabled")
  el.setAttribute("aria-busy", "true")
  const icon = el.querySelector("i.fa")
  if (icon) {
    icon.dataset.idleClass = icon.className
    icon.className = SPINNER_CLASS
  } else {
    const spinner = document.createElement("i")
    spinner.className = `${SPINNER_CLASS} mr-1`
    spinner.dataset.addedSpinner = "1"
    el.prepend(spinner)
  }
}

const clearBusy = () => {
  document.querySelectorAll("[data-busy]").forEach((el) => {
    delete el.dataset.busy
    el.classList.remove("disabled")
    el.removeAttribute("aria-busy")
    el.querySelectorAll("[data-added-spinner]").forEach((spinner) => spinner.remove())
    el.querySelectorAll("[data-idle-class]").forEach((icon) => {
      icon.className = icon.dataset.idleClass
      delete icon.dataset.idleClass
    })
  })
  document.querySelectorAll("form[data-submitting]").forEach((form) => {
    delete form.dataset.submitting
  })
}

// Only plain left clicks navigate this tab; a new-tab click leaves this page idle
const opensInThisTab = (event, link) =>
  event.button === 0 &&
  !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) &&
  (!link.target || link.target === "_self")

const showError = (container) => {
  const alert = document.createElement("div")
  alert.className = "alert alert-danger"
  alert.textContent = container.dataset.error || "Could not load the ticket list."
  const retry = document.createElement("a")
  retry.href = window.location.href
  retry.className = "alert-link ml-2"
  retry.textContent = container.dataset.retry || "Try again"
  alert.append(retry)
  container.replaceChildren(alert)
}

// While a background job (refresh or tag sync) runs, the table reports
// data-pending="1" and is polled again, backing off up to POLL_MAX_MS.
const POLL_FIRST_MS = 1500
const POLL_MAX_MS = 10000
const POLL_GIVE_UP_MS = 10 * 60 * 1000 // background jobs time out after 10 minutes

// Polls must not carry ?refresh=1, or every poll would queue another refresh
const withoutRefresh = (url) => {
  const parsed = new URL(url, window.location.href)
  parsed.searchParams.delete("refresh")
  return parsed.toString()
}

const loadTable = async (container, url = container.dataset.url, poll = null) => {
  try {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
    // A redirect means the session expired: reload to get the login page
    if (response.redirected) return window.location.reload()
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    container.innerHTML = await response.text()
  } catch (e) {
    console.error("pretix ticket table failed to load", e)
    showError(container)
    return
  }
  const pending = container.querySelector('[data-pending="1"]')
  const state = poll || { started: Date.now(), delay: POLL_FIRST_MS }
  if (!pending || Date.now() - state.started > POLL_GIVE_UP_MS) return
  window.setTimeout(() => {
    loadTable(container, withoutRefresh(container.dataset.url), {
      started: state.started,
      delay: Math.min(state.delay * 1.5, POLL_MAX_MS),
    })
  }, state.delay)
}

document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("pretix-tickets")
  if (container) loadTable(container)

  // The table request above already carries ?refresh=1; drop it from the address
  // bar so reloading the page uses the cache instead of refetching from pretix
  const url = new URL(window.location.href)
  if (url.searchParams.has("refresh")) {
    url.searchParams.delete("refresh")
    window.history.replaceState(null, "", url)
  }

  // Delegated, because the table's forms are inserted after load
  document.addEventListener("submit", (event) => {
    const form = event.target
    if (form.dataset.submitting) return event.preventDefault()
    const button = event.submitter
    if (button?.hasAttribute("data-pretix-busy")) {
      form.dataset.submitting = "1"
      showBusy(button)
    }
  })
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-pretix-busy]")
    if (link && !event.defaultPrevented && opensInThisTab(event, link)) showBusy(link)
  })
})

// Coming back via the back/forward cache restores the page as it was left,
// spinners included
window.addEventListener("pageshow", (event) => {
  if (event.persisted) clearBusy()
})
