// SPDX-FileCopyrightText: 2018-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const flashTooltip = (element, message, duration) => {
    const wasTooltip = element.getAttribute('data-toggle') === 'tooltip'
    const oldTooltip = element.dataset.tooltip
    element.dataset.tooltip = message
    if (!wasTooltip) {
        element.setAttribute('data-toggle', 'tooltip')
    }
    setTimeout(() => {
        if (oldTooltip === undefined) {
            delete element.dataset.tooltip
        } else {
            element.dataset.tooltip = oldTooltip
        }
        if (!wasTooltip) {
            element.removeAttribute('data-toggle')
        }
    }, duration)
}

const performCopy = (element) => {
    navigator.clipboard.writeText(element.dataset.destination).then(() => {
        flashTooltip(element, element.dataset.successMessage || 'Copied!', 1000)
    }, () => {
        flashTooltip(element, element.dataset.errorMessage || 'Failed to copy', 2000)
    })
}

onReady(() => {
    document.addEventListener('click', (event) => {
        const element = event.target.closest('.copyable-text')
        if (element) performCopy(element)
    })

    document.addEventListener('keydown', (event) => {
        if (event.key !== ' ' && event.key !== 'Enter') return
        const element = event.target.closest('.copyable-text')
        if (!element) return
        event.preventDefault()
        performCopy(element)
    })
})
