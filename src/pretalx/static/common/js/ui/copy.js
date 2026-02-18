// SPDX-FileCopyrightText: 2018-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

const performCopy = (element) => {
    navigator.clipboard.writeText(element.dataset.destination).then(() => {
        const wasTooltip = element.getAttribute('data-toggle') === 'tooltip'
        const oldTitle = element.title || ''
        element.title = element.dataset.successMessage || 'Copied!'
        if (!wasTooltip) {
            element.setAttribute('data-toggle', 'tooltip')
        }
        setTimeout(() => {
            element.title = oldTitle
            if (!wasTooltip) {
                element.removeAttribute('data-toggle')
            }
        }, 1000)
    }, () => {
        const wasTooltip = element.getAttribute('data-toggle') === 'tooltip'
        const oldTitle = element.title || ''
        element.title = element.dataset.errorMessage || 'Failed to copy'
        if (!wasTooltip) {
            element.setAttribute('data-toggle', 'tooltip')
        }
        setTimeout(() => {
            element.title = oldTitle
            if (!wasTooltip) {
                element.removeAttribute('data-toggle')
            }
        }, 2000)
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
