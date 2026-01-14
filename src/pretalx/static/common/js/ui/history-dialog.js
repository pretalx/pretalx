// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const setupHistoryDialog = () => {
    const dialog = document.getElementById('dialog-history-details')
    if (!dialog) return

    const dialogContent = document.getElementById('dialog-history-details-content')
    if (!dialogContent) return

    const loadingTemplate = dialogContent.querySelector('.dialog-loading')

    document.querySelectorAll('.log-detail[hx-get]').forEach((link) => {
        link.addEventListener('click', function(event) {
            event.preventDefault()
            if (loadingTemplate) {
                const loading = loadingTemplate.cloneNode(true)
                loading.querySelector(".loading-spinner")?.classList.add("loading-spinner-md")
                dialogContent.replaceChildren(loading)
            }
            dialog.showModal()
            window.htmx.process(this)
        })
    })

    dialog.addEventListener('close', () => { dialogContent.innerHTML = '' })
}

onReady(setupHistoryDialog)
