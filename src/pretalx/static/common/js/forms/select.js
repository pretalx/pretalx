// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const isVisible = (element) => {
    if (!element) return false
    return !element.hidden && !element.classList.contains("d-none") && !element.style.display === "none"
}

const validateSelect = (element, addErrors = false) => {
    const container = element.closest('.choices')
    if (!container) return true

    const isRequired = element.hasAttribute('required')
    const hasValue = element.value && element.value !== ''

    if (isRequired && !hasValue) {
        if (addErrors) {
            container.classList.add('is-invalid')
            if (!container.nextElementSibling?.classList.contains('js-validation-error')) {
                const feedback = document.createElement('div')
                feedback.className = 'invalid-feedback js-validation-error'
                feedback.textContent = element.dataset.requiredMessage || 'Please select an option.'
                container.after(feedback)
            }
        }
        return false
    }
    container.classList.remove('is-invalid')
    if (container.nextElementSibling?.classList.contains('js-validation-error')) {
        container.nextElementSibling.remove()
    }
    return true
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
    element.addEventListener('change', () => validateSelect(element))
}

onReady(() => {
    document
        .querySelectorAll("select.enhanced")
        .forEach((element) => initSelect(element))

    document.querySelectorAll('form').forEach(form => {
        // Using click on submit buttons, because when the form is invalid, the browser's native validation
        // will prevent the submit() event from firing. yes, this means that this won't work for enter-submit
        // but I figure something is better than nothing
        form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])').forEach(button => {
            button.addEventListener('click', (e) => {
                if (form.noValidate || button.formNoValidate) return
                let firstInvalid = null
                form.querySelectorAll('select.enhanced[required]').forEach(select => {
                    if (!validateSelect(select, true) && !firstInvalid) firstInvalid = select
                })
                if (firstInvalid) {
                    e.preventDefault()
                    const container = firstInvalid.closest('.choices')
                    container?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                    container?.querySelector('.choices__input')?.focus()
                }
            })
        })
    })
})
