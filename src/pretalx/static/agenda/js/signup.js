// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const SIGNUP_DIALOGS = {
    "#signup": "signup-confirm-dialog",
    "#signup-success": "signup-success-dialog",
}

const clearSignupHash = () => {
    if (!(window.location.hash in SIGNUP_DIALOGS)) return
    const url = window.location.pathname + window.location.search
    history.replaceState(null, "", url)
}

const openDialogFromHash = () => {
    const target = SIGNUP_DIALOGS[window.location.hash]
    if (!target) return
    const dialog = document.getElementById(target)
    if (dialog && !dialog.open) {
        dialog.addEventListener("close", clearSignupHash, { once: true })
        dialog.showModal()
    }
}

onReady(openDialogFromHash)
