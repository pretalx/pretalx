// SPDX-FileCopyrightText: 2025-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const initTagsInput = (element) => {
    const placeholder = element.getAttribute("placeholder") || ""

    const choicesInstance = new Choices(element, {
        removeItems: true,
        removeItemButton: true,
        removeItemButtonAlignLeft: true,
        duplicateItemsAllowed: false,
        delimiter: ",",
        paste: true,
        placeholderValue: placeholder,
        removeItemIconText: "×",
        removeItemLabelText: "",
    })

    const inputElement = choicesInstance.input.element

    const simulateEnter = () => {
        const enterEvent = new KeyboardEvent("keydown", {
            key: "Enter",
            code: "Enter",
            keyCode: 13,
            which: 13,
            bubbles: true,
        })
        inputElement.dispatchEvent(enterEvent)
    }

    // Handle space and comma as delimiters during typing
    inputElement.addEventListener("keydown", (event) => {
        if (event.key === " " || event.key === ",") {
            event.preventDefault()
            simulateEnter()
        }
    })

    // Also add value when leaving the input field
    inputElement.addEventListener("blur", () => {
        if (inputElement.value.trim()) {
            simulateEnter()
        }
    })

    element._choicesInstance = choicesInstance
}

onReady(() => {
    document
        .querySelectorAll("input.tags-input")
        .forEach((element) => initTagsInput(element))
})
