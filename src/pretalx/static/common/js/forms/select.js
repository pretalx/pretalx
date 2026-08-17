// SPDX-FileCopyrightText: 2019-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const isVisible = (element) => {
    if (!element) return false
    return !element.hidden && !element.classList.contains("d-none") && !element.style.display === "none"
}

const validateSelect = (element, addErrors = false) => {
    const container = element.closest('.choices')
    if (!container) return true

    const isRequired = element.dataset.required === "true"
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

const decodeEntities = (value) => {
    if (!value || !value.includes("&")) return value
    const holder = document.createElement("textarea")
    holder.innerHTML = value
    return holder.value
}

const setDecodedLabel = (node, label) => {
    if (!label || !label.includes("&")) return
    const decoded = decodeEntities(label)
    for (const child of node.childNodes) {
        if (child.nodeType === Node.TEXT_NODE && child.data.trim()) {
            if (child.data !== decoded) child.data = decoded
            return
        }
    }
}

const initSelect = (element) => {
    if (element._choicesInstance) return
    const isRequired = element.dataset.required === "true"
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
            !element.readonly && (!isRequired || element.multiple),
        removeItemButtonAlignLeft: true,
        searchFields: (element.dataset.searchFields || "label").split(","),
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
        allowHTML: false,
        position: element.dataset.position || "auto",
    }
    choicesOptions.callbackOnCreateTemplates = (strToEl, escapeForTemplates, getClassNames) => ({
            choice: (allowHTML, choice, _unused, selectedText, groupName) => {
                let originalResult = Choices.defaults.templates.choice(allowHTML, choice, _unused, selectedText, groupName)
                setDecodedLabel(originalResult, choice.label)
                if (choice.element && choice.element.dataset.description && choice.element.dataset.description.length > 0) {
                    const description = document.createElement("div")
                    description.className = "choice-item-description"
                    description.textContent = choice.element.dataset.description
                    originalResult.appendChild(description)
                }
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
                if (choice.element && choice.element.dataset.fontFamily) {
                    const family = choice.element.dataset.fontFamily
                    const sample = choice.element.dataset.fontSample || ""
                    const pangram = document.documentElement.lang === "de"
                        ? "Victor jagt zwölf Boxkämpfer quer über den großen Sylter Deich."
                        : "The quick brown fox jumps over the lazy dog."
                    const preview = document.createElement("div")
                    preview.className = "choice-font-preview"
                    preview.style.fontFamily = `'${family}', sans-serif`
                    preview.textContent = pangram
                    if (sample) {
                        preview.appendChild(document.createElement("br"))
                        preview.appendChild(document.createTextNode(sample))
                    }
                    originalResult.appendChild(preview)
                }
                return originalResult
            },
            item: (_a, choice, removeItemButton) => {
                let originalResult = Choices.defaults.templates.item(_a, choice, removeItemButton)
                setDecodedLabel(originalResult, choice.label)
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
                if (choice.element && choice.element.dataset.fontFamily) {
                    const family = choice.element.dataset.fontFamily
                    originalResult.style.fontFamily = `'${family}', sans-serif`
                }
                return originalResult
            }
    })
    const choicesInstance = new Choices(element, choicesOptions)
    element._choicesInstance = choicesInstance
    if (isRequired) {
        element.closest('.choices')?.setAttribute('aria-required', 'true')
    }
    element.addEventListener('change', () => validateSelect(element))
}

window.initEnhancedSelects = (root = document, { deferred = false } = {}) =>
    root.querySelectorAll("select.enhanced").forEach((element) => {
        if (element._choicesInstance) return
        if (!deferred && element.dataset.deferred !== undefined) return
        initSelect(element)
    })

onReady(() => {
    window.initEnhancedSelects()

    document.querySelectorAll('form').forEach(form => {
        // Using click on submit buttons, because when the form is invalid, the browser's native validation
        // will prevent the submit() event from firing.
        form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])').forEach(button => {
            button.addEventListener('click', (e) => {
                if (form.noValidate || button.formNoValidate) return
                let firstInvalid = null
                form.querySelectorAll('select.enhanced[data-required="true"]').forEach(select => {
                    if (select.closest('[data-formset-form-deleted]')) return
                    if (!validateSelect(select, true) && !firstInvalid) firstInvalid = select
                })
                if (firstInvalid) {
                    e.preventDefault()
                    const container = firstInvalid.closest('.choices')
                    scrollToField(container)
                }
            })
        })
    })
})
