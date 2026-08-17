// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Delegated, and the dialog is looked up per click: the history page patches
// the log list (dialog included) in place when a filter is applied.
onReady(() => {
    let loadingTemplate = null

    document.addEventListener('click', (event) => {
        const link = event.target.closest('.log-detail[hx-get]')
        if (!link) return
        const dialog = document.getElementById('dialog-history-details')
        const dialogContent = document.getElementById('dialog-history-details-content')
        if (!dialog || !dialogContent) return
        event.preventDefault()
        loadingTemplate = loadingTemplate || dialogContent.querySelector('.dialog-loading')
        if (loadingTemplate) {
            const loading = loadingTemplate.cloneNode(true)
            loading.querySelector(".loading-spinner")?.classList.add("loading-spinner-md")
            dialogContent.replaceChildren(loading)
        }
        dialog.showModal()
        window.htmx.process(link)
    })

    document.addEventListener('close', (event) => {
        if (event.target.id === 'dialog-history-details') {
            const dialogContent = document.getElementById('dialog-history-details-content')
            if (dialogContent) dialogContent.innerHTML = ''
        }
    }, true)
})
