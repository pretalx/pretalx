// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const setupExportFormPage = (form) => {
    const picker = setupColumnPicker(form)
    const sort = setupSortSection(form)
    setupExportFormatFields(form)
    window.initEnhancedSelects?.(form, { deferred: true })
    form.addEventListener("submit", () => {
        writeHiddenList(form, "columns", picker.getColumns())
        writeHiddenList(form, "ordering", sort.getOrdering())
    })
}

onReady(() => {
    document.querySelectorAll("form.table-export-form").forEach(setupExportFormPage)
})
