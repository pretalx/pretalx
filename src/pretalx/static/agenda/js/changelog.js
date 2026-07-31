// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const openEntryFromHash = () => {
    if (!window.location.hash) return
    const version = decodeURIComponent(window.location.hash.slice(1))
    const entry = document.getElementById(version)
    if (entry && entry.tagName === "DETAILS") entry.open = true
}

onReady(openEntryFromHash)
window.addEventListener("hashchange", openEntryFromHash)
