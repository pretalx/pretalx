// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const openDropdowns = () => document.querySelectorAll('details.dropdown[open]')

const closeDropdown = (details, refocus) => {
    details.open = false
    if (refocus) details.querySelector('summary')?.focus()
}

document.addEventListener('click', (event) => {
    openDropdowns().forEach((details) => {
        if (!details.contains(event.target)) closeDropdown(details)
    })
})

document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return
    // A dialog opened from a menu item runs first
    if (document.querySelector('dialog[open]')) return
    const open = Array.from(openDropdowns())
    if (!open.length) return
    event.preventDefault()
    open.forEach((details) =>
        closeDropdown(details, details.contains(document.activeElement)),
    )
})
