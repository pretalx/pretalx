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
            dialogContent.innerHTML = '<div class="text-center p-4"><i class="fa fa-spinner fa-spin fa-2x"></i></div>'
            dialog.showModal()
            window.htmx.process(this)
        })
    })

    dialog.addEventListener('close', () => { dialogContent.innerHTML = '' })
}

onReady(setupHistoryDialog)
