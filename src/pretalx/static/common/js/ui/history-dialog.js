// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const setupHistoryDialog = () => {
    const dialog = document.getElementById('dialog-history-details')
    if (!dialog) return

    const dialogContent = document.getElementById('dialog-history-details-content')
    if (!dialogContent) return

    document.querySelectorAll('.log-detail[hx-get]').forEach((link) => {
        link.addEventListener('click', function(event) {
            event.preventDefault()
            window.htmx.process(this)
            dialog.showModal()
        })
    })

    dialog.addEventListener('close', () => { dialogContent.innerHTML = '' })
}

onReady(setupHistoryDialog)
