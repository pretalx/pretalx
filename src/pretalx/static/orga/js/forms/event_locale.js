// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const buildLocaleOptions = (template, allowed) => {
    const result = []
    for (const node of template) {
        if (node.tagName === "OPTGROUP") {
            const group = node.cloneNode(false)
            for (const option of node.children) {
                if (allowed.includes(option.value)) {
                    group.appendChild(option.cloneNode(true))
                }
            }
            if (group.children.length) result.push(group)
        } else if (allowed.includes(node.value)) {
            result.push(node.cloneNode(true))
        }
    }
    return result
}

onReady(() => {
    const localesInput = document.querySelector("select.language-select[multiple]")
    const localeInput = document.querySelector(
        "select.language-select:not([multiple])",
    )
    if (!localesInput || !localeInput) return

    const wrapper = document.querySelector("#event-locale")
    const template = Array.from(localeInput.children).map((node) =>
        node.cloneNode(true),
    )

    const update = () => {
        const allowed = Array.from(localesInput.selectedOptions).map(
            (option) => option.value,
        )
        const current = localeInput.value
        localeInput._choicesInstance?.destroy()
        delete localeInput._choicesInstance
        localeInput.replaceChildren(...buildLocaleOptions(template, allowed))
        localeInput.value = allowed.includes(current) ? current : allowed[0] || ""
        window.initEnhancedSelects?.(localeInput.parentElement, { deferred: true })
        setBlockVisibility(wrapper, allowed.length > 1)
    }

    localesInput.addEventListener("change", update)
    update()
})
