// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const carryFilters = () => {
  const params = new URLSearchParams(window.location.search)
  params.delete("page")
  const query = params.toString()
  document.querySelectorAll("[data-carry-filters]").forEach((link) => {
    const target = new URL(link.href, window.location.href)
    link.href = `${target.pathname}${query ? `?${query}` : ""}`
  })
}

document.addEventListener("htmx:pushedIntoHistory", carryFilters)
