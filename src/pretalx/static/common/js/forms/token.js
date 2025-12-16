// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const handleTokenTable = () => {
    const table = document.querySelector('#create-token #permission-endpoints')
    const presetField = document.querySelector('#id_permission_preset')
    table.style.display = (presetField.value === 'custom') ? 'flex' : 'none'
}

const updateRowAllCheckbox = (endpoint) => {
    const row = document.querySelector(`tr[data-endpoint="${endpoint}"]`)
    const checkboxes = row.querySelectorAll('input[type="checkbox"][data-permission]')
    const rowAllCheckbox = row.querySelector('.permission-row-all')
    const allChecked = Array.from(checkboxes).every(cb => cb.checked)
    rowAllCheckbox.checked = allChecked
}

const updateColAllCheckbox = (permission) => {
    const checkboxes = document.querySelectorAll(`#endpoint-permissions-table tbody input[type="checkbox"][data-permission="${permission}"]`)
    const colAllCheckbox = document.querySelector(`.permission-col-all[data-permission="${permission}"]`)
    const allChecked = Array.from(checkboxes).every(cb => cb.checked)
    colAllCheckbox.checked = allChecked
}

const updateAllCheckboxes = () => {
    document.querySelectorAll('.permission-row-all').forEach(cb => {
        updateRowAllCheckbox(cb.dataset.endpoint)
    })
    document.querySelectorAll('.permission-col-all').forEach(cb => {
        updateColAllCheckbox(cb.dataset.permission)
    })
}

const setupPermissionCheckboxes = () => {
    const table = document.querySelector('#endpoint-permissions-table')
    if (!table) return

    table.querySelectorAll('.permission-row-all').forEach(rowAllCb => {
        rowAllCb.addEventListener('change', () => {
            const endpoint = rowAllCb.dataset.endpoint
            const row = document.querySelector(`tr[data-endpoint="${endpoint}"]`)
            const checkboxes = row.querySelectorAll('input[type="checkbox"][data-permission]')
            checkboxes.forEach(cb => cb.checked = rowAllCb.checked)
            document.querySelectorAll('.permission-col-all').forEach(cb => {
                updateColAllCheckbox(cb.dataset.permission)
            })
        })
    })

    table.querySelectorAll('.permission-col-all').forEach(colAllCb => {
        colAllCb.addEventListener('change', () => {
            const permission = colAllCb.dataset.permission
            const checkboxes = table.querySelectorAll(`input[type="checkbox"][data-permission="${permission}"]`)
            checkboxes.forEach(cb => cb.checked = colAllCb.checked)
            document.querySelectorAll('.permission-row-all').forEach(cb => {
                updateRowAllCheckbox(cb.dataset.endpoint)
            })
        })
    })

    table.querySelectorAll('tbody input[type="checkbox"][data-permission]').forEach(cb => {
        cb.addEventListener('change', () => {
            const row = cb.closest('tr')
            const endpoint = row.dataset.endpoint
            const permission = cb.dataset.permission
            updateRowAllCheckbox(endpoint)
            updateColAllCheckbox(permission)
        })
    })

    updateAllCheckboxes()
}

const setupSelectAllEvents = () => {
    const selectAllButton = document.querySelector('.select-all-events')
    if (!selectAllButton) return

    const selectAllHandler = (event) => {
        event.preventDefault()
        const selectElement = document.querySelector('#id_events')
        if (!selectElement || !selectElement._choicesInstance) return

        const choices = selectElement._choicesInstance
        const allValues = Array.from(selectElement.options).map(option => option.value).filter(v => v)
        choices.setChoiceByValue(allValues)
    }

    selectAllButton.addEventListener('click', selectAllHandler)
    selectAllButton.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            selectAllHandler(event)
        }
    })
}

const setupTokenTable = () => {
    const presetField = document.querySelector('#id_permission_preset')
    presetField.addEventListener('change', handleTokenTable)
    handleTokenTable()
    setupPermissionCheckboxes()
    setupSelectAllEvents()
}

onReady(setupTokenTable)
