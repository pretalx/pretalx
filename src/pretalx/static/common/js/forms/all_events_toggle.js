// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

onReady(() => {
    const allEventsInput = document.querySelector("input#id_all_events")
    const limitEventsContainer = document.querySelector("#limit-events-container")
    if (!allEventsInput || !limitEventsContainer) return

    const updateEventsVisibility = () => {
        setBlockVisibility(limitEventsContainer, !allEventsInput.checked)
    }
    allEventsInput.addEventListener("change", updateEventsVisibility)
    updateEventsVisibility()
})
