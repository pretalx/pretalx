// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const addDateLimit = (element, other, limit) => {
    const otherElement = document.querySelector(other)
    if (otherElement) {
        otherElement.addEventListener("change", () => {
            element.setAttribute(limit, otherElement.value)
        })
        element.setAttribute(limit, otherElement.value)
    }
}

// Handle date and datetime fields:
// - Make sure the picker opens on focus
// - Use the data-date-after and data-date-before attributes to set min/max dynamically on change
const initDateFields = () => {
    document
        .querySelectorAll("input[type=date], input[type=datetime-local]")
        .forEach((element) => {
            if (element.readOnly || element.disabled) return
            // Delay, because otherwise clicking the *icon* in FF will make the picker immediately disappear again
            element.addEventListener("focus", () =>
                setTimeout(() => element.showPicker(), 70),
            )
            if (element.dataset.dateBefore)
                addDateLimit(element, element.dataset.dateBefore, "max")
            if (element.dataset.dateAfter)
                addDateLimit(element, element.dataset.dateAfter, "min")
        })
}

onReady(initDateFields)
