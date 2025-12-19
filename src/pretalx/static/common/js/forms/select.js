// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Validate required enhanced selects before form submission
// This is needed because Choices.js hides the original select element,
// making it unfocusable for browser's native HTML5 validation tooltip.
const validateRequiredEnhancedSelects = (form) => {
    let isValid = true
    form.querySelectorAll('select.enhanced').forEach(select => {
        // Check data-required since we remove the required attribute to prevent
        // browser's native validation (which can't focus hidden elements)
        const isRequired = select.dataset.required === 'true' || select.hasAttribute('required')
        const hasSelection = select.multiple
            ? select.selectedOptions.length > 0
            : select.value !== ''

        const choicesContainer = select.closest('.choices')
        if (!choicesContainer) return

        const wrapper = choicesContainer.parentElement
        const existingError = wrapper.querySelector('.invalid-feedback.js-validation')

        if (isRequired && !hasSelection) {
            isValid = false
            choicesContainer.classList.add('is-invalid')
            if (!existingError) {
                const errorDiv = document.createElement('div')
                errorDiv.className = 'invalid-feedback js-validation'
                errorDiv.style.display = 'block'
                errorDiv.textContent = select.multiple
                    ? 'Please select at least one option.'
                    : 'Please select an option.'
                wrapper.appendChild(errorDiv)
            }
            // Scroll to first invalid field
            if (isValid === false) {
                choicesContainer.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }
        } else {
            choicesContainer.classList.remove('is-invalid')
            if (existingError) existingError.remove()
        }
    })
    return isValid
}

const clearEnhancedSelectError = (select) => {
    const choicesContainer = select.closest('.choices')
    if (!choicesContainer) return

    choicesContainer.classList.remove('is-invalid')
    const wrapper = choicesContainer.parentElement
    const existingError = wrapper.querySelector('.invalid-feedback.js-validation')
    if (existingError) existingError.remove()
}

const isVisible = (element) => {
    if (!element) return false
    return !element.hidden && !element.classList.contains("d-none") && !element.style.display === "none"
}

const initSelect = (element) => {
    const removeItemButton =
        !element.readonly && (!element.required || element.multiple)
    let showPlaceholder = !!element.title
    if (showPlaceholder) {
        // Make sure we don't show a placeholder that is obvious from context
        if (element.getAttribute("aria-describedby")) {
            const describedBy = document.getElementById(
                element.getAttribute("aria-describedby"),
            )
            if (isVisible(describedBy)) {
                showPlaceholder = describedBy.textContent !== element.title
            }
        }
    }
    if (showPlaceholder) {
        const label = document.querySelector(`label[for=${element.id}]`)
        if (isVisible(label)) {
            showPlaceholder = label.textContent !== element.title
        }
    }
    const realPlaceholder = element.getAttribute("placeholder")
    showPlaceholder = showPlaceholder || (realPlaceholder && realPlaceholder.length > 0)
    const choicesOptions = {
        removeItems: !element.readonly,
        removeItemButton:
            !element.readonly && (!element.required || element.multiple),
        removeItemButtonAlignLeft: true,
        searchFields: ["label"],
        searchEnabled: true,
        searchResultLimit: -1,
        resetScrollPosition: false,
        shouldSort: false,
        placeholderValue: showPlaceholder ? (element.title || realPlaceholder) : null,
        itemSelectText: "",
        addItemText: "",
        removeItemLabelText: "×",
        removeItemIconText: "×",
        maxItemText: "",
        allowHTML: true,
        position: element.dataset.position || "auto",
    }
    if (element.querySelectorAll("option[data-description]").length || element.querySelectorAll("option[data-color]").length || element.querySelectorAll("option[data-highlight]").length) {
        choicesOptions.callbackOnCreateTemplates = (strToEl, escapeForTemplates, getClassNames) => ({
            choice: (allowHTML, classNames, choice, selectedText, groupName) => {
                let originalResult = Choices.defaults.templates.choice(allowHTML, classNames, choice, selectedText, groupName)
                if (classNames.element && classNames.element.dataset.description && classNames.element.dataset.description.length > 0) {
                    originalResult.innerHTML += `<div class="choice-item-description">${classNames.element.dataset.description}</div>`
                }
                if (classNames.element && classNames.element.dataset.color && classNames.element.dataset.color.length > 0) {
                    let color = classNames.element.dataset.color
                    if (color.startsWith("--")) {
                        color = `var(${color})`
                    }
                    originalResult.classList.add("choice-item-color")
                    originalResult.style.setProperty("--choice-color", color)
                }
                if (classNames.element && classNames.element.dataset.highlight === "true") {
                    originalResult.classList.add("choice-item-highlight")
                }
                return originalResult
            },
            item: (_a, choice, removeItemButton) => {
                let originalResult = Choices.defaults.templates.item(_a, choice, removeItemButton)
                if (choice.element && choice.element.dataset.color && choice.element.dataset.color.length > 0) {
                    let color = choice.element.dataset.color
                    if (color.startsWith("--")) {
                        color = `var(${color})`
                    }
                    originalResult.classList.add("choice-item-color")
                    originalResult.style.setProperty("--choice-color", color)
                }
                if (choice.element && choice.element.dataset.highlight === "true") {
                    originalResult.classList.add("choice-item-highlight")
                }
                return originalResult
            }
        })
    }
    const choicesInstance = new Choices(element, choicesOptions)
    element._choicesInstance = choicesInstance
}

onReady(() => {
    document
        .querySelectorAll("select.enhanced")
        .forEach((element) => {
            initSelect(element)
            // Clear validation error when user changes selection
            element.addEventListener('change', () => clearEnhancedSelectError(element))
            // Remove HTML required attribute - browser can't focus hidden element for validation.
            // We handle validation ourselves in validateRequiredEnhancedSelects().
            if (element.hasAttribute('required')) {
                element.dataset.required = 'true'
                element.removeAttribute('required')
            }
        })

    // Add form submit validation for all forms with enhanced selects
    document.querySelectorAll('form').forEach(form => {
        if (form.querySelector('select.enhanced')) {
            form.addEventListener('submit', (event) => {
                if (!validateRequiredEnhancedSelects(form)) {
                    event.preventDefault()
                    event.stopPropagation()
                }
            })
        }
    })
})
