// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Preselect the browser's timezone, unless the server already knows better.
onReady(() => {
    const select = document.querySelector("select[data-autofill='timezone']")
    if (!select) return
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
    if (!timezone || timezone === select.value) return
    if (!Array.from(select.options).some((option) => option.value === timezone)) return
    select.value = timezone
    select._choicesInstance?.setChoiceByValue(timezone)
})
