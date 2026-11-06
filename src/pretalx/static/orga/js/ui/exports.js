// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const writeHiddenList = (form, name, values) => {
    form.querySelectorAll(`input[type=hidden][name="${name}"]`).forEach((el) =>
        el.remove(),
    )
    values.forEach((value) => {
        const input = document.createElement("input")
        input.type = "hidden"
        input.name = name
        input.value = value
        form.appendChild(input)
    })
}

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
